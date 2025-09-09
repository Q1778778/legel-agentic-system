"""
Legal Data Processor Service

This service handles data standardization, processing, and transformation
from various legal data APIs into unified formats for GraphRAG integration.
"""

import asyncio
import hashlib
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass
import structlog
from pydantic import BaseModel
import spacy
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer
from textstat import flesch_reading_ease, flesch_kincaid_grade
import textdistance

from .legal_data_apis import LegalCase, LegalDocument, DataSource
from ..models.schemas import Case, Issue, ArgumentSegment

logger = structlog.get_logger()


@dataclass
class ProcessingStats:
    """Statistics from data processing."""
    documents_processed: int
    entities_extracted: int
    citations_found: int
    legal_concepts_identified: int
    processing_time_ms: int
    quality_score: float


class LegalEntity(BaseModel):
    """Extracted legal entity."""
    text: str
    entity_type: str  # PERSON, ORG, CASE, STATUTE, REGULATION, etc.
    confidence: float
    start_pos: int
    end_pos: int
    metadata: Dict[str, Any] = {}


class LegalCitation(BaseModel):
    """Extracted legal citation."""
    citation_text: str
    citation_type: str  # case, statute, regulation, constitution
    authority_level: str  # supreme_court, federal_circuit, state_supreme, etc.
    jurisdiction: Optional[str] = None
    year: Optional[int] = None
    confidence: float
    normalized_form: str


class LegalConcept(BaseModel):
    """Identified legal concept."""
    concept: str
    category: str  # procedural, substantive, constitutional, etc.
    domain: str  # patent, contract, tort, criminal, etc.
    confidence: float
    context: str


class ProcessedLegalDocument(BaseModel):
    """Fully processed legal document."""
    original_doc: Dict[str, Any]
    standardized_metadata: Dict[str, Any]
    extracted_entities: List[LegalEntity]
    extracted_citations: List[LegalCitation]
    identified_concepts: List[LegalConcept]
    text_segments: List[str]
    summary: Optional[str] = None
    key_points: List[str] = []
    quality_metrics: Dict[str, float] = {}
    processing_timestamp: datetime


class LegalDataProcessor:
    """Advanced legal data processor with NLP and standardization capabilities."""
    
    def __init__(self):
        """Initialize the legal data processor."""
        self.logger = logger
        
        # Initialize NLP models
        self._init_nlp_models()
        
        # Legal patterns and vocabulary
        self._init_legal_patterns()
        
        # Processing stats
        self.stats = ProcessingStats(
            documents_processed=0,
            entities_extracted=0,
            citations_found=0,
            legal_concepts_identified=0,
            processing_time_ms=0,
            quality_score=0.0
        )
    
    def _init_nlp_models(self):
        """Initialize NLP models and resources."""
        try:
            # Try to load spaCy model
            try:
                self.nlp = spacy.load("en_core_web_sm")
            except OSError:
                self.logger.warning("spaCy model not found, downloading...")
                import subprocess
                subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"], check=True)
                self.nlp = spacy.load("en_core_web_sm")
            
            # Download NLTK data if needed
            try:
                nltk.data.find('tokenizers/punkt')
            except LookupError:
                nltk.download('punkt')
            
            try:
                nltk.data.find('corpora/stopwords')
            except LookupError:
                nltk.download('stopwords')
            
            self.stop_words = set(stopwords.words('english'))
            
        except Exception as e:
            self.logger.error(f"Error initializing NLP models: {e}")
            # Fallback to basic processing
            self.nlp = None
            self.stop_words = set()
    
    def _init_legal_patterns(self):
        """Initialize legal citation and concept patterns."""
        
        # Citation patterns
        self.citation_patterns = {
            'case_citation': [
                r'\b\d+\s+[A-Za-z\.]+\s+\d+\b',  # 123 F.3d 456
                r'\b\d+\s+U\.?S\.?\s+\d+\b',     # 123 US 456
                r'\b\d+\s+S\.?\s?Ct\.?\s+\d+\b', # 123 S. Ct. 456
                r'\d+\s+F\.\s?(?:2d|3d)\s+\d+',  # Federal reporters
                r'\d+\s+[A-Z][a-z]*\.?\s+(?:2d|3d)?\s+\d+',  # State reporters
            ],
            'statute_citation': [
                r'\b\d+\s+U\.?S\.?C\.?\s+§?\s*\d+',  # 35 USC § 101
                r'\b\d+\s+C\.?F\.?R\.?\s+§?\s*\d+',   # 37 CFR § 1.1
                r'§\s*\d+(?:\.\d+)*',                  # § 123.45
            ],
            'regulation_citation': [
                r'\b\d+\s+Fed\.?\s+Reg\.?\s+\d+',     # Federal Register
                r'\b\d+\s+C\.?F\.?R\.?\s+\d+',        # Code of Federal Regulations
            ]
        }
        
        # Legal concept vocabulary
        self.legal_concepts = {
            'procedural': [
                'motion', 'pleading', 'discovery', 'jurisdiction', 'venue',
                'standing', 'summary judgment', 'due process', 'service'
            ],
            'substantive': [
                'breach', 'damages', 'liability', 'negligence', 'contract',
                'tort', 'patent', 'copyright', 'trademark', 'infringement'
            ],
            'constitutional': [
                'first amendment', 'due process', 'equal protection',
                'commerce clause', 'free speech', 'search and seizure'
            ],
            'evidence': [
                'hearsay', 'relevance', 'prejudicial', 'admissible',
                'authentication', 'best evidence', 'privilege'
            ]
        }
        
        # Domain-specific terms
        self.legal_domains = {
            'patent': ['invention', 'prior art', 'novelty', 'obviousness', 'claims'],
            'contract': ['consideration', 'offer', 'acceptance', 'breach', 'performance'],
            'tort': ['duty', 'breach', 'causation', 'damages', 'negligence'],
            'criminal': ['intent', 'actus reus', 'mens rea', 'burden of proof'],
            'constitutional': ['fundamental rights', 'strict scrutiny', 'rational basis']
        }
    
    async def process_legal_cases(
        self,
        cases: List[LegalCase],
        include_nlp: bool = True,
        include_citations: bool = True,
        include_concepts: bool = True
    ) -> List[ProcessedLegalDocument]:
        """
        Process a batch of legal cases.
        
        Args:
            cases: List of legal cases to process
            include_nlp: Whether to perform NLP analysis
            include_citations: Whether to extract citations
            include_concepts: Whether to identify legal concepts
            
        Returns:
            List of processed documents
        """
        start_time = datetime.now()
        processed_docs = []
        
        for case in cases:
            try:
                processed_doc = await self._process_single_case(
                    case, include_nlp, include_citations, include_concepts
                )
                processed_docs.append(processed_doc)
                self.stats.documents_processed += 1
                
            except Exception as e:
                self.logger.error(f"Error processing case {case.case_id}: {e}")
        
        # Update stats
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        self.stats.processing_time_ms += int(processing_time)
        
        return processed_docs
    
    async def process_legal_documents(
        self,
        documents: List[LegalDocument],
        include_nlp: bool = True,
        include_citations: bool = True,
        include_concepts: bool = True
    ) -> List[ProcessedLegalDocument]:
        """
        Process a batch of legal documents.
        
        Args:
            documents: List of legal documents to process
            include_nlp: Whether to perform NLP analysis
            include_citations: Whether to extract citations
            include_concepts: Whether to identify legal concepts
            
        Returns:
            List of processed documents
        """
        start_time = datetime.now()
        processed_docs = []
        
        for doc in documents:
            try:
                processed_doc = await self._process_single_document(
                    doc, include_nlp, include_citations, include_concepts
                )
                processed_docs.append(processed_doc)
                self.stats.documents_processed += 1
                
            except Exception as e:
                self.logger.error(f"Error processing document {doc.doc_id}: {e}")
        
        # Update stats
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        self.stats.processing_time_ms += int(processing_time)
        
        return processed_docs
    
    async def _process_single_case(
        self,
        case: LegalCase,
        include_nlp: bool,
        include_citations: bool,
        include_concepts: bool
    ) -> ProcessedLegalDocument:
        """Process a single legal case."""
        
        # Combine text content
        text_content = self._extract_text_content(case.dict())
        
        # Extract entities if NLP enabled
        entities = []
        if include_nlp and text_content:
            entities = await self._extract_entities(text_content)
            self.stats.entities_extracted += len(entities)
        
        # Extract citations
        citations = []
        if include_citations and text_content:
            citations = await self._extract_citations(text_content)
            self.stats.citations_found += len(citations)
        
        # Identify legal concepts
        concepts = []
        if include_concepts and text_content:
            concepts = await self._identify_legal_concepts(text_content)
            self.stats.legal_concepts_identified += len(concepts)
        
        # Create text segments
        segments = await self._create_text_segments(text_content)
        
        # Generate summary
        summary = await self._generate_summary(text_content, entities, concepts)
        
        # Extract key points
        key_points = await self._extract_key_points(text_content, entities, concepts)
        
        # Calculate quality metrics
        quality_metrics = await self._calculate_quality_metrics(text_content)
        
        # Standardize metadata
        standardized_metadata = await self._standardize_case_metadata(case)
        
        return ProcessedLegalDocument(
            original_doc=case.dict(),
            standardized_metadata=standardized_metadata,
            extracted_entities=entities,
            extracted_citations=citations,
            identified_concepts=concepts,
            text_segments=segments,
            summary=summary,
            key_points=key_points,
            quality_metrics=quality_metrics,
            processing_timestamp=datetime.now(timezone.utc)
        )
    
    async def _process_single_document(
        self,
        doc: LegalDocument,
        include_nlp: bool,
        include_citations: bool,
        include_concepts: bool
    ) -> ProcessedLegalDocument:
        """Process a single legal document."""
        
        # Extract text content
        text_content = self._extract_text_content(doc.dict())
        
        # Extract entities if NLP enabled
        entities = []
        if include_nlp and text_content:
            entities = await self._extract_entities(text_content)
            self.stats.entities_extracted += len(entities)
        
        # Extract citations
        citations = []
        if include_citations and text_content:
            citations = await self._extract_citations(text_content)
            self.stats.citations_found += len(citations)
        
        # Identify legal concepts
        concepts = []
        if include_concepts and text_content:
            concepts = await self._identify_legal_concepts(text_content)
            self.stats.legal_concepts_identified += len(concepts)
        
        # Create text segments
        segments = await self._create_text_segments(text_content)
        
        # Generate summary
        summary = await self._generate_summary(text_content, entities, concepts)
        
        # Extract key points
        key_points = await self._extract_key_points(text_content, entities, concepts)
        
        # Calculate quality metrics
        quality_metrics = await self._calculate_quality_metrics(text_content)
        
        # Standardize metadata
        standardized_metadata = await self._standardize_document_metadata(doc)
        
        return ProcessedLegalDocument(
            original_doc=doc.dict(),
            standardized_metadata=standardized_metadata,
            extracted_entities=entities,
            extracted_citations=citations,
            identified_concepts=concepts,
            text_segments=segments,
            summary=summary,
            key_points=key_points,
            quality_metrics=quality_metrics,
            processing_timestamp=datetime.now(timezone.utc)
        )
    
    def _extract_text_content(self, doc_data: Dict[str, Any]) -> str:
        """Extract combined text content from document."""
        text_parts = []
        
        # Common text fields to check
        text_fields = ['opinion_text', 'summary', 'text', 'content', 'description']
        
        for field in text_fields:
            if field in doc_data and doc_data[field]:
                text_parts.append(str(doc_data[field]))
        
        # Also check for title/caption
        if 'caption' in doc_data and doc_data['caption']:
            text_parts.append(str(doc_data['caption']))
        elif 'title' in doc_data and doc_data['title']:
            text_parts.append(str(doc_data['title']))
        
        return ' '.join(text_parts)
    
    async def _extract_entities(self, text: str) -> List[LegalEntity]:
        """Extract legal entities from text using NLP."""
        entities = []
        
        if not self.nlp or not text:
            return entities
        
        try:
            doc = self.nlp(text[:1000000])  # Limit text length
            
            for ent in doc.ents:
                # Map spaCy entity types to legal entity types
                legal_type = self._map_entity_type(ent.label_)
                
                entity = LegalEntity(
                    text=ent.text,
                    entity_type=legal_type,
                    confidence=0.8,  # Default confidence for spaCy entities
                    start_pos=ent.start_char,
                    end_pos=ent.end_char,
                    metadata={'spacy_label': ent.label_}
                )
                entities.append(entity)
            
            # Also extract court names and case names using patterns
            court_entities = await self._extract_court_entities(text)
            entities.extend(court_entities)
            
        except Exception as e:
            self.logger.error(f"Error extracting entities: {e}")
        
        return entities
    
    def _map_entity_type(self, spacy_label: str) -> str:
        """Map spaCy entity labels to legal entity types."""
        mapping = {
            'PERSON': 'PERSON',
            'ORG': 'ORGANIZATION',
            'GPE': 'JURISDICTION',
            'DATE': 'DATE',
            'MONEY': 'MONETARY_AMOUNT',
            'LAW': 'LEGAL_AUTHORITY',
            'NORP': 'GROUP'
        }
        return mapping.get(spacy_label, 'OTHER')
    
    async def _extract_court_entities(self, text: str) -> List[LegalEntity]:
        """Extract court names using patterns."""
        entities = []
        
        # Common court patterns
        court_patterns = [
            r'U\.?S\.?\s+(?:Supreme\s+)?Court',
            r'(?:Federal\s+)?Circuit\s+Court',
            r'District\s+Court',
            r'Court\s+of\s+Appeals',
            r'Supreme\s+Court\s+of\s+[A-Z][a-z]+',
            r'[A-Z][a-z]+\s+(?:Superior|Municipal|County)\s+Court'
        ]
        
        for pattern in court_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                entity = LegalEntity(
                    text=match.group(),
                    entity_type='COURT',
                    confidence=0.9,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    metadata={'pattern': pattern}
                )
                entities.append(entity)
        
        return entities
    
    async def _extract_citations(self, text: str) -> List[LegalCitation]:
        """Extract legal citations from text."""
        citations = []
        
        for citation_type, patterns in self.citation_patterns.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text):
                    citation_text = match.group().strip()
                    
                    citation = LegalCitation(
                        citation_text=citation_text,
                        citation_type=citation_type,
                        authority_level=self._determine_authority_level(citation_text),
                        jurisdiction=self._extract_jurisdiction(citation_text),
                        year=self._extract_year(citation_text),
                        confidence=0.8,
                        normalized_form=self._normalize_citation(citation_text)
                    )
                    citations.append(citation)
        
        # Remove duplicates
        seen_citations = set()
        unique_citations = []
        for citation in citations:
            citation_key = citation.normalized_form.lower()
            if citation_key not in seen_citations:
                seen_citations.add(citation_key)
                unique_citations.append(citation)
        
        return unique_citations
    
    def _determine_authority_level(self, citation: str) -> str:
        """Determine the authority level of a citation."""
        citation_lower = citation.lower()
        
        if 'u.s.' in citation_lower or 'sup. ct.' in citation_lower:
            return 'supreme_court'
        elif 'f.3d' in citation_lower or 'f.2d' in citation_lower:
            return 'federal_circuit'
        elif 'f. supp' in citation_lower:
            return 'federal_district'
        else:
            return 'state'
    
    def _extract_jurisdiction(self, citation: str) -> Optional[str]:
        """Extract jurisdiction from citation if possible."""
        # This is a simplified version - would need more sophisticated parsing
        if 'u.s.' in citation.lower():
            return 'federal'
        return None
    
    def _extract_year(self, citation: str) -> Optional[int]:
        """Extract year from citation."""
        year_match = re.search(r'\b(19|20)\d{2}\b', citation)
        if year_match:
            return int(year_match.group())
        return None
    
    def _normalize_citation(self, citation: str) -> str:
        """Normalize citation format."""
        # Remove extra spaces and standardize format
        normalized = re.sub(r'\s+', ' ', citation.strip())
        return normalized
    
    async def _identify_legal_concepts(self, text: str) -> List[LegalConcept]:
        """Identify legal concepts in text."""
        concepts = []
        text_lower = text.lower()
        
        for category, concept_list in self.legal_concepts.items():
            for concept in concept_list:
                if concept.lower() in text_lower:
                    # Find the context around the concept
                    context = self._extract_concept_context(text, concept)
                    
                    # Determine the legal domain
                    domain = self._determine_legal_domain(text, concept)
                    
                    legal_concept = LegalConcept(
                        concept=concept,
                        category=category,
                        domain=domain,
                        confidence=0.7,
                        context=context
                    )
                    concepts.append(legal_concept)
        
        return concepts
    
    def _extract_concept_context(self, text: str, concept: str) -> str:
        """Extract context around a legal concept."""
        concept_pos = text.lower().find(concept.lower())
        if concept_pos == -1:
            return ""
        
        # Get surrounding context (100 chars before and after)
        start = max(0, concept_pos - 100)
        end = min(len(text), concept_pos + len(concept) + 100)
        
        return text[start:end].strip()
    
    def _determine_legal_domain(self, text: str, concept: str) -> str:
        """Determine the legal domain based on context."""
        text_lower = text.lower()
        
        # Check for domain-specific terms
        domain_scores = {}
        for domain, terms in self.legal_domains.items():
            score = sum(1 for term in terms if term.lower() in text_lower)
            if score > 0:
                domain_scores[domain] = score
        
        if domain_scores:
            return max(domain_scores, key=domain_scores.get)
        
        return 'general'
    
    async def _create_text_segments(self, text: str) -> List[str]:
        """Create meaningful text segments."""
        if not text:
            return []
        
        try:
            # Split into sentences
            sentences = sent_tokenize(text)
            
            # Group sentences into paragraphs/segments
            segments = []
            current_segment = []
            
            for sentence in sentences:
                current_segment.append(sentence)
                
                # Create segment when we have 3-5 sentences or hit a natural break
                if (len(current_segment) >= 5 or 
                    any(phrase in sentence.lower() for phrase in ['however', 'therefore', 'in conclusion'])):
                    segments.append(' '.join(current_segment))
                    current_segment = []
            
            # Add remaining sentences
            if current_segment:
                segments.append(' '.join(current_segment))
            
            return segments
            
        except Exception as e:
            self.logger.error(f"Error creating text segments: {e}")
            # Fallback: split by double newlines or periods
            return [seg.strip() for seg in re.split(r'\n\n|\.{2,}', text) if seg.strip()]
    
    async def _generate_summary(
        self,
        text: str,
        entities: List[LegalEntity],
        concepts: List[LegalConcept]
    ) -> Optional[str]:
        """Generate a summary of the document."""
        if not text:
            return None
        
        try:
            # Simple extractive summary using first few sentences and key concepts
            sentences = sent_tokenize(text)[:3]  # First 3 sentences
            
            # Add key legal concepts
            key_concepts = [c.concept for c in concepts[:5]]  # Top 5 concepts
            
            summary_parts = sentences.copy()
            if key_concepts:
                summary_parts.append(f"Key legal concepts: {', '.join(key_concepts)}")
            
            return ' '.join(summary_parts)
            
        except Exception as e:
            self.logger.error(f"Error generating summary: {e}")
            return text[:500] + "..." if len(text) > 500 else text
    
    async def _extract_key_points(
        self,
        text: str,
        entities: List[LegalEntity],
        concepts: List[LegalConcept]
    ) -> List[str]:
        """Extract key points from the document."""
        key_points = []
        
        if not text:
            return key_points
        
        try:
            # Extract sentences with legal significance indicators
            sentences = sent_tokenize(text)
            
            significance_indicators = [
                'held that', 'ruled that', 'concluded that', 'found that',
                'the court', 'therefore', 'accordingly', 'in conclusion',
                'it is', 'we find', 'the defendant', 'the plaintiff'
            ]
            
            for sentence in sentences:
                sentence_lower = sentence.lower()
                if any(indicator in sentence_lower for indicator in significance_indicators):
                    if len(sentence) < 200:  # Reasonable length
                        key_points.append(sentence.strip())
                
                if len(key_points) >= 5:  # Limit to 5 key points
                    break
            
            return key_points
            
        except Exception as e:
            self.logger.error(f"Error extracting key points: {e}")
            return []
    
    async def _calculate_quality_metrics(self, text: str) -> Dict[str, float]:
        """Calculate quality metrics for the document."""
        metrics = {}
        
        if not text:
            return metrics
        
        try:
            # Basic text statistics
            word_count = len(word_tokenize(text))
            sentence_count = len(sent_tokenize(text))
            
            metrics['word_count'] = float(word_count)
            metrics['sentence_count'] = float(sentence_count)
            metrics['avg_words_per_sentence'] = word_count / max(sentence_count, 1)
            
            # Readability metrics
            try:
                metrics['flesch_reading_ease'] = flesch_reading_ease(text)
                metrics['flesch_kincaid_grade'] = flesch_kincaid_grade(text)
            except:
                metrics['flesch_reading_ease'] = 0.0
                metrics['flesch_kincaid_grade'] = 0.0
            
            # Legal content density (percentage of legal terms)
            legal_term_count = 0
            words = [word.lower() for word in word_tokenize(text)]
            
            all_legal_terms = []
            for category_terms in self.legal_concepts.values():
                all_legal_terms.extend(category_terms)
            for domain_terms in self.legal_domains.values():
                all_legal_terms.extend(domain_terms)
            
            for term in all_legal_terms:
                legal_term_count += words.count(term.lower())
            
            metrics['legal_content_density'] = legal_term_count / max(word_count, 1)
            
            # Overall quality score (0-1)
            quality_factors = [
                min(1.0, word_count / 100),  # Sufficient content
                min(1.0, metrics['legal_content_density'] * 10),  # Legal relevance
                1.0 if 30 <= metrics['flesch_reading_ease'] <= 70 else 0.5,  # Readability
            ]
            
            metrics['overall_quality'] = sum(quality_factors) / len(quality_factors)
            
        except Exception as e:
            self.logger.error(f"Error calculating quality metrics: {e}")
            metrics['overall_quality'] = 0.5  # Default score
        
        return metrics
    
    async def _standardize_case_metadata(self, case: LegalCase) -> Dict[str, Any]:
        """Standardize case metadata."""
        metadata = {
            'id': case.case_id,
            'type': 'case',
            'source': case.source.value,
            'title': case.caption,
            'court': case.court,
            'jurisdiction': case.jurisdiction,
            'filed_date': case.filed_date.isoformat() if case.filed_date else None,
            'decided_date': case.decided_date.isoformat() if case.decided_date else None,
            'docket_number': case.docket_number,
            'parties': case.parties,
            'judges': case.judges,
            'citations': case.citations,
            'precedents': case.precedents,
            'outcome': case.metadata.get('outcome'),
            'status': case.metadata.get('status'),
            'url': case.metadata.get('absolute_url') or case.metadata.get('frontend_url'),
            'processing_date': datetime.now(timezone.utc).isoformat()
        }
        
        return {k: v for k, v in metadata.items() if v is not None}
    
    async def _standardize_document_metadata(self, doc: LegalDocument) -> Dict[str, Any]:
        """Standardize document metadata."""
        metadata = {
            'id': doc.doc_id,
            'type': doc.doc_type,
            'source': doc.source.value,
            'title': doc.title,
            'agency': doc.agency,
            'effective_date': doc.effective_date.isoformat() if doc.effective_date else None,
            'citations': doc.citations,
            'url': doc.url,
            'processing_date': datetime.now(timezone.utc).isoformat()
        }
        
        # Add source-specific metadata
        if doc.metadata:
            metadata.update(doc.metadata)
        
        return {k: v for k, v in metadata.items() if v is not None}
    
    def get_processing_stats(self) -> ProcessingStats:
        """Get current processing statistics."""
        return self.stats
    
    def reset_stats(self):
        """Reset processing statistics."""
        self.stats = ProcessingStats(
            documents_processed=0,
            entities_extracted=0,
            citations_found=0,
            legal_concepts_identified=0,
            processing_time_ms=0,
            quality_score=0.0
        )


# Utility functions for data quality assessment
class DataQualityAssessor:
    """Assess quality of processed legal data."""
    
    @staticmethod
    def assess_document_completeness(doc: ProcessedLegalDocument) -> float:
        """Assess how complete a document is (0-1)."""
        required_fields = ['title', 'text', 'source', 'date']
        present_fields = 0
        
        original = doc.original_doc
        if original.get('caption') or original.get('title'):
            present_fields += 1
        if original.get('opinion_text') or original.get('text'):
            present_fields += 1
        if original.get('source'):
            present_fields += 1
        if original.get('filed_date') or original.get('decided_date') or original.get('effective_date'):
            present_fields += 1
        
        return present_fields / len(required_fields)
    
    @staticmethod
    def assess_citation_quality(citations: List[LegalCitation]) -> float:
        """Assess quality of extracted citations (0-1)."""
        if not citations:
            return 0.0
        
        quality_score = 0.0
        for citation in citations:
            score = 0.0
            
            # Check citation format
            if re.search(r'\d+', citation.citation_text):
                score += 0.3
            if citation.jurisdiction:
                score += 0.2
            if citation.year:
                score += 0.2
            if citation.confidence > 0.7:
                score += 0.3
            
            quality_score += min(1.0, score)
        
        return quality_score / len(citations)
    
    @staticmethod
    def assess_entity_relevance(entities: List[LegalEntity]) -> float:
        """Assess relevance of extracted entities (0-1)."""
        if not entities:
            return 0.0
        
        legal_entity_types = {'PERSON', 'COURT', 'ORGANIZATION', 'CASE', 'STATUTE'}
        relevant_entities = sum(1 for e in entities if e.entity_type in legal_entity_types)
        
        return relevant_entities / len(entities)


# Example usage and testing
async def test_processor():
    """Test the legal data processor."""
    from .legal_data_apis import LegalCase, DataSource
    
    # Create test case
    test_case = LegalCase(
        case_id="test_001",
        source=DataSource.COURTLISTENER,
        caption="Test Corp v. Example LLC - Patent Infringement Case",
        court="U.S. District Court for the Northern District of California",
        jurisdiction="federal",
        opinion_text="The court finds that defendant's product infringes claim 1 of the '123 patent. Under 35 U.S.C. § 271, the defendant is liable for patent infringement. The plaintiff has established a prima facie case of infringement.",
        citations=["35 U.S.C. § 271", "123 F.3d 456"],
    )
    
    # Initialize processor
    processor = LegalDataProcessor()
    
    # Process the case
    processed_docs = await processor.process_legal_cases([test_case])
    
    if processed_docs:
        doc = processed_docs[0]
        print(f"Processed document: {doc.standardized_metadata['title']}")
        print(f"Entities found: {len(doc.extracted_entities)}")
        print(f"Citations found: {len(doc.extracted_citations)}")
        print(f"Concepts identified: {len(doc.identified_concepts)}")
        print(f"Quality score: {doc.quality_metrics.get('overall_quality', 0):.2f}")


if __name__ == "__main__":
    asyncio.run(test_processor())
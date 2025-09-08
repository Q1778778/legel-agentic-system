#!/usr/bin/env python3
"""
Data import system for Court Argument Simulator.
Creates sample Chinese legal cases and loads them into GraphRAG databases.
"""

import asyncio
import uuid
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import sys
import random
import logging

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent / "src"))

from src.core.config import settings
from src.db.vector_db import VectorDB
from src.db.graph_db import GraphDB
from src.services.embeddings import EmbeddingService
from src.models.schemas import (
    ArgumentBundle,
    Case,
    Lawyer,
    Judge,
    Issue,
    Citation,
    ArgumentSegment,
    ConfidenceScore,
    GraphExplanation,
    StageType,
    DispositionType,
    RoleType,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChineseLegalDataGenerator:
    """Generate realistic Chinese legal case data."""
    
    def __init__(self):
        # Initialize basic data first
        self.courts = [
            "北京市第一中级人民法院", "上海市高级人民法院", "广州市中级人民法院",
            "深圳市中级人民法院", "杭州市中级人民法院", "南京市中级人民法院",
            "成都市中级人民法院", "武汉市中级人民法院", "西安市中级人民法院",
            "最高人民法院", "天津市高级人民法院", "重庆市高级人民法院"
        ]
        self.jurisdictions = ["北京", "上海", "广东", "浙江", "江苏", "四川", "湖北", "陕西", "天津", "重庆"]
        
        # Then initialize pools that depend on the basic data
        self.lawyers_pool = self._generate_lawyers()
        self.judges_pool = self._generate_judges()
        self.issues_pool = self._generate_issues()
    
    def _generate_lawyers(self) -> List[Dict[str, Any]]:
        """Generate pool of lawyers."""
        lawyers = []
        law_firms = [
            "金杜律师事务所", "君合律师事务所", "中伦律师事务所", "海问律师事务所",
            "方达律师事务所", "锦天城律师事务所", "德恒律师事务所", "盈科律师事务所",
            "大成律师事务所", "康达律师事务所", "环球律师事务所", "通商律师事务所"
        ]
        
        names = [
            "张伟", "李娜", "王强", "刘敏", "陈杰", "杨静", "赵磊", "孙丽",
            "周勇", "吴红", "徐明", "朱华", "胡亮", "高峰", "林雪", "何军",
            "郭涛", "马超", "韩冰", "曹阳", "田野", "石磊", "夏雨", "秦风",
            "易建联", "贺明", "谢霆锋", "董卿", "汪涵", "李佳琦"
        ]
        
        for i, name in enumerate(names):
            lawyers.append({
                "id": f"lawyer_{i+1:03d}",
                "name": name,
                "bar_id": f"BJ{random.randint(100000, 999999)}",
                "firm": random.choice(law_firms)
            })
        
        return lawyers
    
    def _generate_judges(self) -> List[Dict[str, Any]]:
        """Generate pool of judges."""
        judges = []
        judge_names = [
            "张建国", "李明华", "王德伟", "刘志强", "陈建华", "杨立新", "赵春梅", "孙建军",
            "周立波", "吴国庆", "徐志远", "朱建华", "胡锦涛", "高建华", "林志玲", "何建国",
            "郭德纲", "马化腾", "韩红梅", "曹志明", "田建华", "石国强", "夏志华", "秦建国"
        ]
        
        for i, name in enumerate(judge_names):
            judges.append({
                "id": f"judge_{i+1:03d}",
                "name": f"{name}法官",
                "court": random.choice(self.courts)
            })
        
        return judges
    
    def _generate_issues(self) -> List[Dict[str, Any]]:
        """Generate pool of legal issues."""
        issues = [
            # Contract Law Issues
            {
                "id": "issue_contract_001",
                "title": "合同违约损害赔偿",
                "taxonomy_path": ["民法", "合同法", "违约责任", "损害赔偿"]
            },
            {
                "id": "issue_contract_002",
                "title": "合同解除条件",
                "taxonomy_path": ["民法", "合同法", "合同解除"]
            },
            {
                "id": "issue_contract_003",
                "title": "格式条款效力",
                "taxonomy_path": ["民法", "合同法", "格式条款"]
            },
            {
                "id": "issue_contract_004",
                "title": "合同履行抗辩权",
                "taxonomy_path": ["民法", "合同法", "合同履行", "抗辩权"]
            },
            
            # Intellectual Property Issues
            {
                "id": "issue_ip_001",
                "title": "商标侵权认定",
                "taxonomy_path": ["知识产权法", "商标法", "商标侵权"]
            },
            {
                "id": "issue_ip_002",
                "title": "专利权保护范围",
                "taxonomy_path": ["知识产权法", "专利法", "专利权保护"]
            },
            {
                "id": "issue_ip_003",
                "title": "著作权合理使用",
                "taxonomy_path": ["知识产权法", "著作权法", "合理使用"]
            },
            {
                "id": "issue_ip_004",
                "title": "不正当竞争行为",
                "taxonomy_path": ["知识产权法", "反不正当竞争法"]
            },
            
            # Labor Law Issues
            {
                "id": "issue_labor_001",
                "title": "劳动合同解除",
                "taxonomy_path": ["劳动法", "劳动合同", "合同解除"]
            },
            {
                "id": "issue_labor_002",
                "title": "加班费计算",
                "taxonomy_path": ["劳动法", "工资待遇", "加班费"]
            },
            {
                "id": "issue_labor_003",
                "title": "工伤认定",
                "taxonomy_path": ["劳动法", "工伤保险", "工伤认定"]
            },
            {
                "id": "issue_labor_004",
                "title": "经济补偿金",
                "taxonomy_path": ["劳动法", "劳动合同", "经济补偿"]
            },
            
            # Criminal Law Issues
            {
                "id": "issue_criminal_001",
                "title": "故意伤害罪构成要件",
                "taxonomy_path": ["刑法", "侵犯人身权利罪", "故意伤害罪"]
            },
            {
                "id": "issue_criminal_002",
                "title": "盗窃罪数额认定",
                "taxonomy_path": ["刑法", "侵犯财产罪", "盗窃罪"]
            },
            {
                "id": "issue_criminal_003",
                "title": "正当防卫界限",
                "taxonomy_path": ["刑法", "犯罪构成", "正当防卫"]
            },
            {
                "id": "issue_criminal_004",
                "title": "共同犯罪认定",
                "taxonomy_path": ["刑法", "犯罪构成", "共同犯罪"]
            },
            
            # Property Rights Issues
            {
                "id": "issue_property_001",
                "title": "房屋买卖合同纠纷",
                "taxonomy_path": ["民法", "物权法", "房屋买卖"]
            },
            {
                "id": "issue_property_002",
                "title": "物权确认",
                "taxonomy_path": ["民法", "物权法", "物权确认"]
            },
            {
                "id": "issue_property_003",
                "title": "相邻关系纠纷",
                "taxonomy_path": ["民法", "物权法", "相邻关系"]
            },
            
            # Company Law Issues
            {
                "id": "issue_company_001",
                "title": "股东权益保护",
                "taxonomy_path": ["商法", "公司法", "股东权益"]
            },
            {
                "id": "issue_company_002",
                "title": "董事责任认定",
                "taxonomy_path": ["商法", "公司法", "董事责任"]
            },
            {
                "id": "issue_company_003",
                "title": "公司解散清算",
                "taxonomy_path": ["商法", "公司法", "公司解散"]
            }
        ]
        
        return issues

    def generate_case_data(self, num_cases: int = 30) -> List[Dict[str, Any]]:
        """Generate realistic Chinese legal case data."""
        cases = []
        
        case_templates = {
            "contract": {
                "captions": [
                    "{}有限公司诉{}有限公司合同纠纷案",
                    "{}公司与{}公司买卖合同争议案",
                    "{}集团诉{}企业合同违约案",
                    "{}贸易公司与{}制造公司供货合同纠纷案"
                ],
                "outcomes": ["胜诉", "败诉", "部分胜诉", "调解", "撤诉"],
                "arguments": [
                    "根据《合同法》第107条规定，当事人一方不履行合同义务或者履行合同义务不符合约定的，应当承担继续履行、采取补救措施或者赔偿损失等违约责任。本案中，被告明确表示不再履行合同，构成根本违约。",
                    "依据《合同法》第94条，当事人一方有下列情形之一的，对方可以解除合同：（一）因不可抗力致使不能实现合同目的。本案疫情期间的特殊情况构成不可抗力，应当免除违约责任。",
                    "根据《民法典》第563条规定，有下列情形之一的，当事人可以解除合同。被告的行为已经严重影响了合同目的的实现，原告有权解除合同并要求赔偿损失。",
                    "《合同法》第60条规定，当事人应当按照约定全面履行自己的义务。当事人应当遵循诚实信用原则，根据合同的性质、目的和交易习惯履行通知、协助、保密等义务。"
                ]
            },
            "ip": {
                "captions": [
                    "{}公司诉{}公司商标侵权纠纷案",
                    "{}科技与{}网络著作权侵权案",
                    "{}研究院诉{}公司专利侵权案",
                    "{}品牌与{}企业不正当竞争案"
                ],
                "outcomes": ["停止侵权", "赔偿损失", "驳回诉讼请求", "调解和解"],
                "arguments": [
                    "根据《商标法》第57条规定，未经商标注册人的许可，在同一种商品上使用与其注册商标相同的商标的，属于侵犯注册商标专用权。被告的行为构成直接侵权。",
                    "依据《著作权法》第22条，在下列情况下使用作品，可以不经著作权人许可，不向其支付报酬，但应当指明作者姓名、作品名称。被告使用构成合理使用。",
                    "《专利法》第11条规定，发明和实用新型专利权被授予后，除本法另有规定的以外，任何单位或者个人未经专利权人许可，都不得实施其专利。被告产品落入原告专利权保护范围。",
                    "根据《反不正当竞争法》第2条，经营者在生产经营活动中，应当遵循自愿、平等、公平、诚信的原则，遵守法律和商业道德。被告行为违反诚实信用原则。"
                ]
            },
            "labor": {
                "captions": [
                    "{}诉{}公司劳动争议案",
                    "{}与{}集团劳动合同纠纷案",
                    "{}诉{}企业工伤赔偿案",
                    "{}与{}公司加班费争议案"
                ],
                "outcomes": ["支持劳动者", "支持用人单位", "部分支持", "调解结案"],
                "arguments": [
                    "根据《劳动合同法》第39条规定，劳动者有下列情形之一的，用人单位可以解除劳动合同。但用人单位应当履行举证责任，证明劳动者存在严重违纪行为。",
                    "《劳动法》第44条规定，有下列情形之一的，用人单位应当按照下列标准支付高于劳动者正常工作时间工资的工资报酬：（一）安排劳动者延长时间的，支付不低于工资的百分之一百五十的工资报酬。",
                    "依据《工伤保险条例》第14条，职工有下列情形之一的，应当认定为工伤。本案事故发生在工作时间和工作场所内，符合工伤认定条件。",
                    "《劳动合同法》第47条规定，经济补偿按劳动者在本单位工作的年限，每满一年支付一个月工资的标准向劳动者支付。违法解除应支付二倍经济补偿。"
                ]
            },
            "criminal": {
                "captions": [
                    "人民检察院诉{}故意伤害案",
                    "人民检察院诉{}盗窃案",
                    "人民检察院诉{}诈骗案",
                    "人民检察院诉{}危险驾驶案"
                ],
                "outcomes": ["有罪", "无罪", "免予刑事处罚", "缓刑"],
                "arguments": [
                    "根据《刑法》第234条规定，故意伤害他人身体的，处三年以下有期徒刑、拘役或者管制。被告人的行为符合故意伤害罪的构成要件，应当依法承担刑事责任。",
                    "依据《刑法》第20条，为了使国家、公共利益、本人或者他人的人身、财产和其他权利免受正在进行的不法侵害，而采取的制止不法侵害的行为，对不法侵害人造成损害的，属于正当防卫。",
                    "《刑法》第264条规定，盗窃公私财物，数额较大的，或者多次盗窃、入户盗窃、携带凶器盗窃、扒窃的，处三年以下有期徒刑、拘役或者管制。被告行为构成盗窃罪。",
                    "根据《刑事诉讼法》第195条，在被告人最后陈述后，审判长宣布休庭，合议庭进行评议，根据已经查明的事实、证据和有关的法律规定，分别作出判决。"
                ]
            }
        }
        
        companies = ["华为", "腾讯", "阿里巴巴", "百度", "小米", "字节跳动", "美团", "滴滴", "京东", "网易", "新浪", "搜狐"]
        people_names = ["张三", "李四", "王五", "赵六", "刘七", "陈八", "杨九", "孙十"]
        
        for i in range(num_cases):
            case_type = random.choice(list(case_templates.keys()))
            template = case_templates[case_type]
            
            # Generate case details
            if case_type == "criminal":
                plaintiff = "北京市人民检察院"
                defendant = random.choice(people_names)
                caption = random.choice(template["captions"]).format(defendant)
            else:
                plaintiff = random.choice(companies)
                defendant = random.choice(companies)
                while defendant == plaintiff:
                    defendant = random.choice(companies)
                caption = random.choice(template["captions"]).format(plaintiff, defendant)
            
            # Select related issue
            issue_candidates = [issue for issue in self.issues_pool 
                             if case_type in issue["taxonomy_path"][0].lower() or 
                                case_type in issue["id"]]
            if not issue_candidates:
                issue_candidates = self.issues_pool[:5]  # Fallback
            
            issue = random.choice(issue_candidates)
            lawyer = random.choice(self.lawyers_pool)
            judge = random.choice(self.judges_pool)
            
            case_data = {
                "case": {
                    "id": f"case_{i+1:03d}",
                    "caption": caption,
                    "court": judge["court"],
                    "jurisdiction": random.choice(self.jurisdictions),
                    "judge_id": judge["id"],
                    "judge_name": judge["name"],
                    "filed_date": self._random_date(),
                    "outcome": random.choice(template["outcomes"])
                },
                "lawyer": lawyer,
                "judge": judge,
                "issue": issue,
                "argument_text": random.choice(template["arguments"]),
                "case_type": case_type
            }
            
            cases.append(case_data)
        
        return cases
    
    def _random_date(self) -> datetime:
        """Generate random date within the last 5 years."""
        start_date = datetime.now() - timedelta(days=5*365)
        end_date = datetime.now() - timedelta(days=30)
        random_days = random.randint(0, (end_date - start_date).days)
        return start_date + timedelta(days=random_days)


class DataImporter:
    """Import generated legal data into GraphRAG databases."""
    
    def __init__(self):
        self.vector_db = VectorDB()
        self.graph_db = GraphDB()
        self.embedding_service = EmbeddingService()
        self.generator = ChineseLegalDataGenerator()
    
    async def import_all_data(self, num_cases: int = 30):
        """Import all generated data into databases."""
        logger.info(f"Starting import of {num_cases} legal cases...")
        
        # Generate case data
        logger.info("Generating case data...")
        case_data = self.generator.generate_case_data(num_cases)
        
        # Create argument bundles
        logger.info("Creating argument bundles...")
        bundles = []
        for case in case_data:
            bundle = await self._create_argument_bundle(case)
            if bundle:
                bundles.append(bundle)
        
        logger.info(f"Created {len(bundles)} argument bundles")
        
        # Import to graph database
        logger.info("Importing to graph database...")
        await self._import_to_graph(bundles)
        
        # Import to vector database
        logger.info("Importing to vector database...")
        await self._import_to_vector(bundles)
        
        logger.info(f"Successfully imported {len(bundles)} cases")
    
    async def _create_argument_bundle(self, case_data: Dict[str, Any]) -> Optional[ArgumentBundle]:
        """Create argument bundle from case data."""
        try:
            # Create models from data
            case = Case(**case_data["case"])
            lawyer = Lawyer(**case_data["lawyer"])
            issue = Issue(**case_data["issue"])
            
            # Create argument segments
            argument_id = f"arg_{uuid.uuid4().hex[:8]}"
            segments = await self._create_segments(argument_id, case_data["argument_text"])
            
            # Create citations (sample)
            citations = self._generate_citations(case_data["case_type"])
            
            # Create confidence score
            confidence = ConfidenceScore(
                value=random.uniform(0.7, 0.95),
                explanation=GraphExplanation(
                    graph_hops=["Issue→Argument", "Argument→Case"],
                    boosts={"relevance": 0.1, "recency": 0.05},
                    final_score=random.uniform(0.7, 0.95)
                ),
                features={"vector_similarity": 0.8, "graph_connectivity": 0.2}
            )
            
            # Create bundle
            bundle = ArgumentBundle(
                argument_id=argument_id,
                confidence=confidence,
                case=case,
                lawyer=lawyer,
                issue=issue,
                stage=random.choice(list(StageType)),
                disposition=random.choice(list(DispositionType)),
                citations=citations,
                segments=segments,
                signature_hash=hashlib.md5(case_data["argument_text"].encode()).hexdigest(),
                tenant="default"
            )
            
            return bundle
            
        except Exception as e:
            logger.error(f"Error creating argument bundle: {e}")
            return None
    
    async def _create_segments(self, argument_id: str, text: str) -> List[ArgumentSegment]:
        """Create argument segments from text."""
        # Split text into logical segments
        sentences = text.split("。")
        segments = []
        
        for i, sentence in enumerate(sentences):
            if sentence.strip():
                segment = ArgumentSegment(
                    segment_id=f"seg_{argument_id}_{i+1:02d}",
                    argument_id=argument_id,
                    text=sentence.strip() + "。",
                    role=RoleType.OPENING if i == 0 else RoleType.ANSWER,
                    seq=i,
                    citations=self._extract_citations(sentence),
                    score=random.uniform(0.6, 0.9)
                )
                segments.append(segment)
        
        return segments
    
    def _extract_citations(self, text: str) -> List[str]:
        """Extract citations from text (simplified)."""
        citations = []
        # Look for law references
        if "《" in text and "》" in text:
            start = text.find("《")
            end = text.find("》", start)
            if end > start:
                law_ref = text[start:end+1]
                citations.append(law_ref)
        
        # Look for article references
        if "第" in text and "条" in text:
            import re
            pattern = r'第\d+条'
            matches = re.findall(pattern, text)
            citations.extend(matches)
        
        return citations
    
    def _generate_citations(self, case_type: str) -> List[Citation]:
        """Generate relevant citations based on case type."""
        citation_map = {
            "contract": [
                Citation(text="《中华人民共和国民法典》", type="statute"),
                Citation(text="《中华人民共和国合同法》", type="statute"),
                Citation(text="最高人民法院关于适用《中华人民共和国合同法》若干问题的解释(一)", type="regulation"),
            ],
            "ip": [
                Citation(text="《中华人民共和国商标法》", type="statute"),
                Citation(text="《中华人民共和国专利法》", type="statute"),
                Citation(text="《中华人民共和国著作权法》", type="statute"),
            ],
            "labor": [
                Citation(text="《中华人民共和国劳动法》", type="statute"),
                Citation(text="《中华人民共和国劳动合同法》", type="statute"),
                Citation(text="《工伤保险条例》", type="regulation"),
            ],
            "criminal": [
                Citation(text="《中华人民共和国刑法》", type="statute"),
                Citation(text="《中华人民共和国刑事诉讼法》", type="statute"),
            ]
        }
        
        return citation_map.get(case_type, [])
    
    async def _import_to_graph(self, bundles: List[ArgumentBundle]):
        """Import bundles to graph database."""
        for i, bundle in enumerate(bundles):
            try:
                success = self.graph_db.upsert_nodes_and_edges(bundle, tenant="default")
                if success:
                    logger.info(f"Imported bundle {i+1}/{len(bundles)} to graph DB")
                else:
                    logger.warning(f"Failed to import bundle {bundle.argument_id} to graph DB")
            except Exception as e:
                logger.error(f"Error importing bundle {bundle.argument_id} to graph: {e}")
    
    async def _import_to_vector(self, bundles: List[ArgumentBundle]):
        """Import bundles to vector database."""
        for i, bundle in enumerate(bundles):
            try:
                # Generate embeddings for segments
                segment_texts = [seg.text for seg in bundle.segments]
                embeddings = await self.embedding_service.embed_batch(segment_texts)
                
                # Create metadata
                metadata = {
                    "tenant": bundle.tenant,
                    "lawyer": {
                        "id": bundle.lawyer.id if bundle.lawyer else None,
                        "name": bundle.lawyer.name if bundle.lawyer else None,
                        "firm": bundle.lawyer.firm if bundle.lawyer else None,
                    },
                    "case": {
                        "id": bundle.case.id,
                        "caption": bundle.case.caption,
                        "court": bundle.case.court,
                        "jurisdiction": bundle.case.jurisdiction,
                        "judge_id": bundle.case.judge_id,
                        "judge_name": bundle.case.judge_name,
                        "filed_date": bundle.case.filed_date.isoformat() if bundle.case.filed_date else None,
                        "outcome": bundle.case.outcome,
                    },
                    "issue": {
                        "id": bundle.issue.id,
                        "title": bundle.issue.title,
                        "taxonomy_path": bundle.issue.taxonomy_path,
                    },
                    "stage": bundle.stage.value if bundle.stage else None,
                    "disposition": bundle.disposition.value if bundle.disposition else None,
                    "filed_year": bundle.case.filed_date.year if bundle.case.filed_date else None,
                    "signature_hash": bundle.signature_hash,
                    "src": "generated_chinese_legal_data"
                }
                
                # Upload to vector DB
                success = self.vector_db.upsert_segments(bundle.segments, embeddings, metadata)
                if success:
                    logger.info(f"Imported bundle {i+1}/{len(bundles)} to vector DB")
                else:
                    logger.warning(f"Failed to import bundle {bundle.argument_id} to vector DB")
                    
            except Exception as e:
                logger.error(f"Error importing bundle {bundle.argument_id} to vector: {e}")


async def main():
    """Main import function."""
    print("🏛️  Court Argument Simulator - Data Import System")
    print("="*60)
    
    try:
        # Initialize importer
        importer = DataImporter()
        
        # Check database connections
        print("Checking database connections...")
        
        # Test vector DB
        try:
            info = importer.vector_db.get_collection_info()
            print(f"✅ Vector DB connected - Collection: {info['name']}, Vector size: {info['vector_size']}")
        except Exception as e:
            print(f"❌ Vector DB connection failed: {e}")
            return
        
        # Test graph DB
        try:
            with importer.graph_db.driver.session() as session:
                result = session.run("RETURN 'Graph DB Connected' as status")
                print(f"✅ Graph DB connected - {result.single()['status']}")
        except Exception as e:
            print(f"❌ Graph DB connection failed: {e}")
            return
        
        # Import data
        num_cases = 30
        print(f"\nImporting {num_cases} Chinese legal cases...")
        await importer.import_all_data(num_cases)
        
        print("\n✅ Data import completed successfully!")
        
        # Show summary
        try:
            vector_info = importer.vector_db.get_collection_info()
            print(f"\n📊 Import Summary:")
            print(f"   Vector DB points: {vector_info['points_count']}")
            print(f"   Collection status: {vector_info['status']}")
            
            with importer.graph_db.driver.session() as session:
                result = session.run("""
                    MATCH (n) 
                    RETURN 
                        count(DISTINCT n) as total_nodes,
                        count(DISTINCT CASE WHEN 'Case' IN labels(n) THEN n END) as cases,
                        count(DISTINCT CASE WHEN 'Argument' IN labels(n) THEN n END) as arguments,
                        count(DISTINCT CASE WHEN 'Lawyer' IN labels(n) THEN n END) as lawyers,
                        count(DISTINCT CASE WHEN 'Judge' IN labels(n) THEN n END) as judges,
                        count(DISTINCT CASE WHEN 'Issue' IN labels(n) THEN n END) as issues
                """)
                stats = result.single()
                print(f"   Graph DB nodes: {stats['total_nodes']}")
                print(f"   Cases: {stats['cases']}, Arguments: {stats['arguments']}")
                print(f"   Lawyers: {stats['lawyers']}, Judges: {stats['judges']}, Issues: {stats['issues']}")
                
        except Exception as e:
            logger.error(f"Error getting summary stats: {e}")
        
    except Exception as e:
        logger.error(f"Import failed: {e}")
        raise
    finally:
        # Cleanup
        if 'importer' in locals():
            importer.graph_db.close()


if __name__ == "__main__":
    asyncio.run(main())
#!/usr/bin/env python3
"""
MCP Demo Script - Shows MCP servers are configured and ready.
MCP servers use stdio protocol and need MCP clients to connect.
"""

import json
import os
from pathlib import Path

def show_mcp_servers():
    """Display available MCP servers."""
    
    print("=" * 60)
    print("MCP (Model Context Protocol) Servers Status")
    print("=" * 60)
    
    # Check MCP Lawyer Server
    lawyer_path = Path("mcp_lawyer_server")
    if lawyer_path.exists():
        print("\n✅ MCP Lawyer Server")
        print("   Status: Available")
        print("   Protocol: stdio")
        print("   Tools:")
        print("   - start_conversation: Begin legal consultation")
        print("   - send_message: Continue legal discussion")
        print("   - get_case_analysis: Analyze legal cases")
        print("   - get_legal_advice: Get legal recommendations")
        
        # Check config
        config_file = lawyer_path / "config.yaml"
        if config_file.exists():
            print("   Config: Found")
    else:
        print("\n❌ MCP Lawyer Server: Not found")
    
    # Check MCP Case Extractor
    extractor_path = Path("mcp_case_extractor")
    if extractor_path.exists():
        print("\n✅ MCP Case Extractor")
        print("   Status: Available")
        print("   Protocol: stdio")
        print("   Tools:")
        print("   - extract_case_info: Extract case information")
        print("   - parse_legal_document: Parse legal documents")
        print("   - identify_parties: Identify parties in case")
        print("   - extract_claims: Extract legal claims")
        
        # Check config
        config_file = extractor_path / "config.yaml"
        if config_file.exists():
            print("   Config: Found")
    else:
        print("\n❌ MCP Case Extractor: Not found")
    
    print("\n" + "=" * 60)
    print("MCP Integration Status")
    print("=" * 60)
    print("""
The MCP servers are configured for stdio communication protocol.
They are designed to be connected by MCP-compatible clients like:
- Claude Desktop App
- VS Code with MCP extension
- Custom MCP clients

For this demo, the MCP functionality is shown in the UI
but actual MCP server processes run on-demand when connected.

The system continues to work with GraphRAG, Neo4j, and Qdrant
for legal analysis without requiring active MCP processes.
""")

if __name__ == "__main__":
    show_mcp_servers()
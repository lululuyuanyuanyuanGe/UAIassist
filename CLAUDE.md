# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ExcelAssist is an AI-powered table processing system designed to help village committees and administrators automate Excel form filling tasks. The system intelligently processes uploaded templates and data files to generate filled forms for various administrative purposes like subsidies, insurance registrations, and demographic records.

## Commands

### Environment Setup
```bash
# Install dependencies with conda
conda env create -f environment.yml
conda activate YaxinAiAssist

# Or install with pip (dependencies listed in environment.yml under pip section)
pip install anthropic langchain langgraph gradio openpyxl pandas beautifulsoup4 selenium
```

### Running the Application
```bash
# Run the main fillout agent
python run_fillout_agent.py

# Run the main driver agent
python agents/DriverAgent.py

# Test HTML generation
python test_html_generation.py
python test_html_simple.py
```

### LibreOffice Document Conversion
The system uses LibreOffice for document conversion (as shown in coomand.txt):
```bash
# Convert DOC to TXT
"D:\LibreOffice\program\soffice.exe" --headless --convert-to "txt:Text (encoded):UTF8" "input.doc" --outdir "output_dir"

# Convert DOC to HTML
"D:\LibreOffice\program\soffice.exe" --headless --convert-to html "input.doc" --outdir "output_dir"
```

## Architecture

### Multi-Agent System with LangGraph
The system implements a sophisticated agent-based architecture using LangGraph's StateGraph with conditional routing:

1. **DriverAgent** (`agents/DriverAgent.py`) - Main orchestrator using `FrontdeskState` 
2. **ProcessUserInputAgent** (`agents/processUserInput.py`) - User interaction with file validation pipeline
3. **RecallFilesAgent** (`agents/recallFilesAgent.py`) - Village-scoped file management with automatic classification
4. **FilloutTableAgent** (`agents/filloutTable.py`) - Parallel data processing with strategy-based table handling
5. **DesignExcelAgent** (`agents/designExcelAgent.py`) - LLM-powered template generation

### State Management Architecture

**FrontdeskState** - Central orchestration state:
```python
chat_history: list[str]           # Conversation tracking
messages: list[BaseMessage]       # LangChain message flow  
template_structure: str           # JSON template analysis
previous_node: str               # Error recovery routing
session_id: str                  # Session isolation
headers_mapping: dict            # Field mappings between template/data
recalled_xls_files: list[str]    # Selected data sources
village_name: str                # Multi-tenant namespacing
```

**Conditional Routing Patterns**:
- **Graceful Degradation**: Complex template processing falls back to simple handling
- **JSON-Based Routing**: LLM responses determine next workflow steps
- **Error Recovery**: JSON parsing failures trigger user clarification loops
- **Tool Detection**: Routes based on LLM tool calls vs direct responses

### File Organization & Session Management

**Session Structure**:
```
conversations/{session_id}/
├── user_uploaded_files/template/  # Template files
├── CSV_files/                     # Generated data
└── output/                        # Final HTML results
```

**Village Data Registry** (`agents/data.json`):
- Village-namespaced file metadata with deduplication
- Automatic file classification (表格/文档)
- Timestamp tracking and file size monitoring
- Template structure analysis caching

### Data Processing Pipeline

**Template Analysis Flow**:
1. File upload → Content extraction → LLM-powered complexity assessment
2. Structure parsing → Multi-level header extraction → Field identification  
3. HTML component generation → User validation → Final storage

**Data Integration Strategies**:
- **多表整合** (Multi-table Integration): Different data sources → unified template
- **多表合并** (Multi-table Merge): Similar structures → combined dataset
- Automatic strategy detection based on template requirements
- Parallel CSV generation with configurable chunking

### Key Architectural Patterns

**Custom State Reducers**: Lambda-based state updates for concurrent operations
**Village-Centric Architecture**: All operations scoped by village for multi-tenancy  
**LLM-Powered Decision Trees**: Dynamic routing based on model analysis
**Parallel Processing**: Concurrent HTML extraction and CSV generation
**Debug Infrastructure**: Comprehensive emoji-based logging throughout workflow

## Development and Debugging

### Debug Features
The system includes comprehensive debugging infrastructure:
- **Emoji-based Logging**: Consistent `🚀 开始执行`, `✅ 执行完成` patterns throughout all agents
- **State Inspection**: Detailed state dumps at each node transition with JSON formatting
- **Error Recovery**: Graceful JSON parsing failure handling with user fallback flows
- **Progress Tracking**: Visual progress indicators for concurrent operations

### Session and State Debugging
```python
# Common debugging patterns found throughout codebase:
print(f"🔍 Debug - template_file_path_raw: {template_file_path} (type: {type(template_file_path)})")
print(f"📊 summary_message测试: {summary_message}")
print(f"🔄 路由决定: {next_node}")
```

### Configuration Details
- **Model Selection**: Configurable between OpenAI (gpt-4o) and SiliconFlow endpoints
- **Temperature Control**: Default 0.2 for consistent outputs, configurable per call
- **Chunking Strategy**: Configurable chunk sizes for large dataset processing  
- **Windows Encoding**: Automatic `chcp 65001` for Chinese character support
- **Rate Limit Handling**: Automatic retry with exponential backoff for HTTP 429 errors

### Rate Limiting and Error Handling

**Automatic Rate Limit Recovery**: All model invoke functions (`invoke_model`, `invoke_model_with_tools`, `invoke_model_with_screenshot`) now include automatic rate limit handling:

- **Error Detection**: Automatically detects HTTP 429 "Too Many Requests" errors
- **Retry-After Support**: Respects server-provided retry-after headers when available
- **Exponential Backoff**: Uses exponential backoff with jitter (1s → 2s → 4s → 8s → 16s → 60s max)
- **Configurable Retries**: Default 5 retry attempts before final failure
- **Graceful Degradation**: Non-rate-limit errors fail immediately without retries

**Supported Error Patterns**:
- OpenAI: `RateLimitError` exceptions and HTTP 429 responses with retry-after headers
- SiliconFlow: HTTP 429 responses following standard retry-after header conventions
- Generic: String matching for "rate limit", "too many requests", "429" in error messages

## Environment Variables

Set the following environment variables:
- `OPENAI_API_KEY` - For OpenAI models (gpt-4o, etc.)
- `SILICONFLOW_API_KEY` - For other models via SiliconFlow API

## Development Notes

### Key Implementation Details
- **Windows-Specific**: Designed for Windows with LibreOffice integration and console encoding handling
- **Session-Based Architecture**: All operations scoped by session ID for concurrent user support  
- **Village Multi-Tenancy**: Data isolation by village name for administrative boundary support
- **Bilingual Codebase**: Mixed English/Chinese comments and variables for local administrative use
- **LLM-Driven Workflows**: Heavy reliance on language models for decision making and content analysis

### Extending the System
When adding new agents or modifying workflows:
1. Follow the TypedDict state pattern with custom reducers for concurrent operations
2. Implement emoji-based logging for consistency with existing debug infrastructure  
3. Add conditional routing logic with graceful degradation fallbacks
4. Ensure session ID threading and village namespacing for data isolation
5. Include JSON parsing error handling with user clarification flows
```

## Project Environment Notes

### System Configuration
- We are running the program under Windows system, with conda to manage our environment
- The environment is configured as: `PS D:\asianInfo\ExcelAssist> & D:/anaconda/envs/YaxinAiAssist/python.exe`
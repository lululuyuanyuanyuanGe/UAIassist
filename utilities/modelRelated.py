from typing import Dict, List, Optional, Any, TypedDict, Annotated
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage
import os
import time
import threading
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError


# Cross-platform timeout context manager using threading
@contextmanager
def execution_timeout(seconds):
    """Context manager to enforce total execution timeout (Windows compatible)"""
    timeout_occurred = threading.Event()
    
    def timeout_handler():
        timeout_occurred.set()
    
    # Start a timer that will set the timeout flag after specified seconds
    timer = threading.Timer(seconds, timeout_handler)
    timer.start()
    
    try:
        yield timeout_occurred
    finally:
        # Cancel the timer
        timer.cancel()


def invoke_model(model_name : str, messages : List[BaseMessage], temperature: float = 0.2) -> str:
    """调用大模型"""
    print(f"🚀 开始调用LLM: {model_name} (temperature={temperature})")
    start_time = time.time()
    
    llm = ChatOpenAI(
        model = model_name,
        api_key=os.getenv("SILICONFLOW_API_KEY"), 
        base_url="https://api.siliconflow.cn/v1",
        streaming=True,
        temperature=temperature,
        request_timeout=30  # 30 seconds network timeout
    )

    full_response = ""

    try:
        total_tokens_used = {"input": 0, "output": 0, "total": 0}
        
        # Use execution timeout context manager for total time control
        with execution_timeout(360) as timeout_flag:  # 360 seconds total execution limit
            for chunk in llm.stream(messages):
                # Check if timeout occurred
                if timeout_flag.is_set():
                    raise TimeoutError(f"LLM execution exceeded 360 seconds")
                
                chunk_content = chunk.content
                print(chunk_content, end="", flush=True)
                full_response += chunk_content
                
                # Extract token usage if available in chunk
                if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                    usage = chunk.usage_metadata
                    total_tokens_used["input"] = usage.get('input_tokens', 0)
                    total_tokens_used["output"] = usage.get('output_tokens', 0)
                    total_tokens_used["total"] = usage.get('total_tokens', 0)
            
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Print timing and token usage
        print(f"\n⏱️ LLM调用完成，耗时: {execution_time:.2f}秒")
        if total_tokens_used["total"] > 0:
            print(f"📊 Token使用: 输入={total_tokens_used['input']:,} | 输出={total_tokens_used['output']:,} | 总计={total_tokens_used['total']:,}")
        
    except TimeoutError as e:
        end_time = time.time()
        execution_time = end_time - start_time
        print(f"\n⏰ LLM调用超时，耗时: {execution_time:.2f}秒，错误: {e}")
        
        # Print any token usage that was captured before timeout
        if total_tokens_used["total"] > 0:
            print(f"📊 超时前Token使用: 输入={total_tokens_used['input']:,} | 输出={total_tokens_used['output']:,} | 总计={total_tokens_used['total']:,}")
        
        raise
    except Exception as e:
        end_time = time.time()
        execution_time = end_time - start_time
        print(f"\n❌ LLM调用失败，耗时: {execution_time:.2f}秒，错误: {e}")
        
        # Print any token usage that was captured before failure
        if total_tokens_used["total"] > 0:
            print(f"📊 失败前Token使用: 输入={total_tokens_used['input']:,} | 输出={total_tokens_used['output']:,} | 总计={total_tokens_used['total']:,}")
        
        raise
    
    return full_response

def invoke_model_with_tools(model_name : str, messages : List[BaseMessage], tools : List[str], temperature: float = 0.2) -> Any:
    """调用大模型并使用工具"""
    print(f"🚀 开始调用LLM(带工具): {model_name} (temperature={temperature})")
    start_time = time.time()
    
    
    
    if model_name.startswith("gpt-"):  # ChatGPT 系列模型
        print("🔍 使用 OpenAI ChatGPT 模型")
        base_url = "https://api.openai.com/v1"
        api_key = os.getenv("OPENAI_API_KEY")
    else:  # 其他模型，例如 deepseek, siliconflow...
        print("🔍 使用 SiliconFlow 模型")
        base_url = "https://api.siliconflow.cn/v1"
        api_key = os.getenv("SILICONFLOW_API_KEY")

    llm = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        streaming=False,
        temperature=temperature,
        timeout=200
    )
    
    try:
        # 绑定工具到模型
        llm_with_tools = llm.bind_tools(tools)
        
        print("📤 正在调用LLM...")
        
        # Use ThreadPoolExecutor for better timeout handling of blocking invoke() call
        def call_llm():
            return llm_with_tools.invoke(messages)
        
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(call_llm)
            try:
                response = future.result(timeout=360)  # 360 seconds timeout
            except FuturesTimeoutError:
                # Cancel the future if it's still running
                future.cancel()
                raise TimeoutError(f"LLM execution exceeded 360 seconds")
        
        print("📥 LLM响应接收完成")
        
        # 打印响应内容（如果有）
        if response.content:
            print(f"\n💬 LLM回复内容:")
            print(response.content)
        
        # Extract token usage information
        token_usage = {"input": 0, "output": 0, "total": 0, "reasoning": 0}
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage = response.usage_metadata
            token_usage["input"] = usage.get('input_tokens', 0)
            token_usage["output"] = usage.get('output_tokens', 0)
            token_usage["total"] = usage.get('total_tokens', 0)
            
            # Check for reasoning tokens (for reasoning models like Qwen3-32B)
            if 'output_token_details' in usage and usage['output_token_details']:
                token_usage["reasoning"] = usage['output_token_details'].get('reasoning', 0)
        
        # 检查是否有工具调用
        if hasattr(response, 'tool_calls') and response.tool_calls:
            print(f"\n🔧 检测到 {len(response.tool_calls)} 个工具调用:")
            
            # 打印每个工具调用的详细信息
            for i, tool_call in enumerate(response.tool_calls):
                print(f"\n📋 工具调用 {i+1}:")
                print(f"   🔧 工具名称: {tool_call.get('name', 'unknown')}")
                
                # 提取工具参数
                args = tool_call.get('args', {})
                print(f"   📝 参数: {args}")
                
                # 如果是用户交互工具，特别显示问题
                if tool_call.get('name') == 'request_user_clarification':
                    question = args.get('question', '')
                    context = args.get('context', '')
                    if question:
                        print(f"\n💬 ⭐ 用户问题: {question}")
                        if context:
                            print(f"📖 上下文: {context}")
                elif tool_call.get('name') == '_collect_user_input':
                    print(f"\n🔄 将收集用户输入信息")
                    session_id = args.get('session_id', '')
                    if session_id:
                        print(f"📋 会话ID: {session_id}")
            
            end_time = time.time()
            execution_time = end_time - start_time
            print(f"\n⏱️ LLM调用完成(带工具调用)，耗时: {execution_time:.2f}秒")
        else:
            end_time = time.time()
            execution_time = end_time - start_time
            print(f"\n⏱️ LLM调用完成(无工具调用)，耗时: {execution_time:.2f}秒")
        
        # Print token usage information
        if token_usage["total"] > 0:
            print(f"📊 Token使用: 输入={token_usage['input']:,} | 输出={token_usage['output']:,} | 总计={token_usage['total']:,}")
            if token_usage["reasoning"] > 0:
                print(f"🧠 推理Token: {token_usage['reasoning']:,} (内部推理过程)")
                visible_output = token_usage["output"] - token_usage["reasoning"]
                print(f"👀 可见输出Token: {visible_output:,}")
        else:
            print("⚠️ 未能获取Token使用信息")
        
        # 返回完整响应以便调用者处理
        return response
        
    except TimeoutError as e:
        end_time = time.time()
        execution_time = end_time - start_time
        print(f"\n⏰ LLM调用超时，耗时: {execution_time:.2f}秒，错误: {e}")
        
        # Try to extract token usage even from timed out requests
        if 'response' in locals() and hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage = response.usage_metadata
            input_tokens = usage.get('input_tokens', 0)
            output_tokens = usage.get('output_tokens', 0)
            total_tokens = usage.get('total_tokens', 0)
            print(f"📊 超时前Token使用: 输入={input_tokens:,} | 输出={output_tokens:,} | 总计={total_tokens:,}")
        
        raise
    except Exception as e:
        end_time = time.time()
        execution_time = end_time - start_time
        print(f"\n❌ LLM调用失败，耗时: {execution_time:.2f}秒，错误: {e}")
        
        # Try to extract token usage even from failed requests
        if 'response' in locals() and hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage = response.usage_metadata
            input_tokens = usage.get('input_tokens', 0)
            output_tokens = usage.get('output_tokens', 0)
            total_tokens = usage.get('total_tokens', 0)
            print(f"📊 失败前Token使用: 输入={input_tokens:,} | 输出={output_tokens:,} | 总计={total_tokens:,}")
        
        import traceback
        traceback.print_exc()
        raise
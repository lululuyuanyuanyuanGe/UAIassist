from typing import Dict, List, Optional, Any, TypedDict, Annotated
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.chat_models import ChatOllama
import re

def model_creation(model_name: str, temperature: float = 0.7, **kwargs):
    """
    This function is used to create a model instance based on the name of the model.
    It supports multiple providers: OpenAI, Anthropic (Claude), Google, DeepSeek, and Ollama (local models).
    
    Args:
        model_name (str): The name of the model (e.g., "gpt-4o", "claude-3-sonnet", "gemini-pro", "deepseek-chat")
        temperature (float): Temperature setting for the model (default: 0.7)
        **kwargs: Additional keyword arguments to pass to the model constructor
            For DeepSeek models, you can also pass:
            - base_url (str): Custom base URL (default: "https://api.deepseek.com")
            - api_key (str): DeepSeek API key (or set DEEPSEEK_API_KEY environment variable)
        
    Returns:
        Callable model instance based on the provider
        
    Raises:
        ValueError: If the model name is not recognized or supported
        
    Examples:
        # OpenAI models
        model = model_creation("gpt-4o")
        
        # Anthropic models
        model = model_creation("claude-3-sonnet-20240229")
        
        # Google models  
        model = model_creation("gemini-pro")
        
        # DeepSeek models
        model = model_creation("deepseek-chat")
        model = model_creation("deepseek-coder", api_key="your-deepseek-key")
        
        # Local models
        model = model_creation("llama2")
    """
    
    # Normalize model name to lowercase for comparison
    model_lower = model_name.lower()
    
    # OpenAI models
    openai_patterns = [
        r'^gpt-.*',           # GPT models (gpt-4, gpt-4o, gpt-3.5-turbo, etc.)
        r'^text-davinci-.*',  # Legacy text models
        r'^davinci.*',        # Davinci models
        r'^curie.*',          # Curie models
        r'^babbage.*',        # Babbage models
        r'^ada.*',            # Ada models
        r'^o1.*',             # O1 models (o1-preview, o1-mini)
    ]
    
    # Anthropic models
    anthropic_patterns = [
        r'^claude-.*',        # Claude models (claude-3-sonnet, claude-3-haiku, etc.)
        r'^claude.*',         # Any claude variant
    ]
    
    # Google models
    google_patterns = [
        r'^gemini-.*',        # Gemini models (gemini-pro, gemini-1.5-pro, etc.)
        r'^palm-.*',          # PaLM models
        r'^bard.*',           # Bard (legacy)
    ]
    
    # DeepSeek models
    deepseek_patterns = [
        r'^deepseek-.*',      # DeepSeek models (deepseek-chat, deepseek-coder, etc.)
        r'^deepseek.*',       # Any deepseek variant
    ]
    
    # Local/Ollama models (common open-source models)
    ollama_patterns = [
        r'^llama.*',          # Llama models (llama2, llama3, etc.)
        r'^mistral.*',        # Mistral models
        r'^codellama.*',      # Code Llama models
        r'^vicuna.*',         # Vicuna models
        r'^alpaca.*',         # Alpaca models
        r'^dolphin.*',        # Dolphin models
        r'^orca.*',           # Orca models
        r'^neural-chat.*',    # Neural Chat models
        r'^starling.*',       # Starling models
        r'^zephyr.*',         # Zephyr models
    ]
    
    def matches_patterns(text: str, patterns: List[str]) -> bool:
        """Check if text matches any of the given regex patterns"""
        return any(re.match(pattern, text, re.IGNORECASE) for pattern in patterns)
    
    try:
        # Check for OpenAI models
        if matches_patterns(model_lower, openai_patterns):
            return ChatOpenAI(model=model_name, temperature=temperature, **kwargs)
        
        # Check for Anthropic models
        elif matches_patterns(model_lower, anthropic_patterns):
            return ChatAnthropic(model=model_name, temperature=temperature, **kwargs)
        
        # Check for Google models
        elif matches_patterns(model_lower, google_patterns):
            return ChatGoogleGenerativeAI(model=model_name, temperature=temperature, **kwargs)
        
        # Check for DeepSeek models (uses OpenAI-compatible API)
        elif matches_patterns(model_lower, deepseek_patterns):
            # DeepSeek uses OpenAI-compatible API with custom base_url
            deepseek_kwargs = {
                'base_url': kwargs.pop('base_url', 'https://api.deepseek.com'),
                'api_key': kwargs.pop('api_key', None),  # Will use DEEPSEEK_API_KEY env var if not provided
                **kwargs
            }
            return ChatOpenAI(model=model_name, temperature=temperature, **deepseek_kwargs)
        
        # Check for Ollama/local models
        elif matches_patterns(model_lower, ollama_patterns):
            return ChatOllama(model=model_name, temperature=temperature, **kwargs)
        
        # If no pattern matches, try to infer from model name keywords
        else:
            # Fallback: check for provider keywords in model name
            if any(keyword in model_lower for keyword in ['openai', 'gpt']):
                return ChatOpenAI(model=model_name, temperature=temperature, **kwargs)
            elif any(keyword in model_lower for keyword in ['anthropic', 'claude']):
                return ChatAnthropic(model=model_name, temperature=temperature, **kwargs)
            elif any(keyword in model_lower for keyword in ['google', 'gemini', 'palm', 'bard']):
                return ChatGoogleGenerativeAI(model=model_name, temperature=temperature, **kwargs)
            elif any(keyword in model_lower for keyword in ['deepseek']):
                deepseek_kwargs = {
                    'base_url': kwargs.pop('base_url', 'https://api.deepseek.com'),
                    'api_key': kwargs.pop('api_key', None),
                    **kwargs
                }
                return ChatOpenAI(model=model_name, temperature=temperature, **deepseek_kwargs)
            elif any(keyword in model_lower for keyword in ['ollama', 'local']):
                return ChatOllama(model=model_name, temperature=temperature, **kwargs)
            else:
                # Default to OpenAI if no clear provider is detected
                print(f"Warning: Could not detect provider for model '{model_name}'. Defaulting to OpenAI.")
                return ChatOpenAI(model=model_name, temperature=temperature, **kwargs)
                
    except ImportError as e:
        raise ImportError(f"Required package not installed for model '{model_name}': {e}")
    except Exception as e:
        raise ValueError(f"Failed to create model instance for '{model_name}': {e}")


def get_supported_providers() -> Dict[str, List[str]]:
    """
    Returns a dictionary of supported providers and their example model names.
    
    Returns:
        Dict mapping provider names to lists of example model names
    """
    return {
        "openai": [
            "gpt-4o", "gpt-4", "gpt-4-turbo", "gpt-3.5-turbo", 
            "gpt-4o-mini", "o1-preview", "o1-mini"
        ],
        "anthropic": [
            "claude-3-sonnet-20240229", "claude-3-haiku-20240307", 
            "claude-3-opus-20240229", "claude-2.1", "claude-instant-1.2"
        ],
        "google": [
            "gemini-pro", "gemini-1.5-pro", "gemini-1.5-flash", 
            "palm-2-chat-bison", "palm-2-codechat-bison"
        ],
        "deepseek": [
            "deepseek-chat", "deepseek-coder", "deepseek-math", 
            "deepseek-v2", "deepseek-v2.5", "deepseek-r1"
        ],
        "ollama": [
            "llama2", "llama3", "mistral", "codellama", "vicuna", 
            "alpaca", "dolphin", "orca", "neural-chat", "starling", "zephyr"
        ]
    }


def detect_provider(model_name: str) -> str:
    """
    Detect the provider for a given model name.
    
    Args:
        model_name (str): The model name to analyze
        
    Returns:
        str: The detected provider name ("openai", "anthropic", "google", "ollama", or "unknown")
    """
    model_lower = model_name.lower()
    
    # OpenAI patterns
    if any(re.match(pattern, model_lower, re.IGNORECASE) for pattern in [
        r'^gpt-.*', r'^text-davinci-.*', r'^davinci.*', r'^curie.*', 
        r'^babbage.*', r'^ada.*', r'^o1.*'
    ]):
        return "openai"
    
    # Anthropic patterns
    elif any(re.match(pattern, model_lower, re.IGNORECASE) for pattern in [
        r'^claude-.*', r'^claude.*'
    ]):
        return "anthropic"
    
    # Google patterns
    elif any(re.match(pattern, model_lower, re.IGNORECASE) for pattern in [
        r'^gemini-.*', r'^palm-.*', r'^bard.*'
    ]):
        return "google"
    
    # DeepSeek patterns
    elif any(re.match(pattern, model_lower, re.IGNORECASE) for pattern in [
        r'^deepseek-.*', r'^deepseek.*'
    ]):
        return "deepseek"
    
    # Ollama patterns
    elif any(re.match(pattern, model_lower, re.IGNORECASE) for pattern in [
        r'^llama.*', r'^mistral.*', r'^codellama.*', r'^vicuna.*', 
        r'^alpaca.*', r'^dolphin.*', r'^orca.*', r'^neural-chat.*', 
        r'^starling.*', r'^zephyr.*'
    ]):
        return "ollama"
    
    else:
        return "unknown"
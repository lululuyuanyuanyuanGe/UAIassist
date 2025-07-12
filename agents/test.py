from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from utilities.modelRelated import invoke_model

response = invoke_model(model_name="gpt-4o", messages=[
    SystemMessage(content="You are a helpful assistant."),
    HumanMessage(content="What is the capital of France?")
])
print(response)






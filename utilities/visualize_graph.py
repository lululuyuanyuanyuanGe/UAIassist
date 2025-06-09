def save_graph_visualization(graph, filename="graph_visualization.png"):
    """Save LangGraph visualization using Mermaid (no pygraphviz needed)"""
    try:
        # Use Mermaid instead of pygraphviz
        png_bytes = graph.get_graph().draw_mermaid_png()
        
        with open(filename, "wb") as f:
            f.write(png_bytes)
        
        print(f"✅ Graph visualization saved as '{filename}'")
        
    except Exception as e:
        print(f"❌ Error: {e}")

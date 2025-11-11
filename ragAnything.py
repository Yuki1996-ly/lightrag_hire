import asyncio
from raganything import RAGAnything
from lightrag import LightRAG
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc
from lightrag.kg.shared_storage import initialize_pipeline_status
import os


async def load_existing_lightrag():
    # First, create or load an existing LightRAG instance
    # Prefer environment variable, fallback to Windows absolute path for consistency
    lightrag_working_dir = os.environ.get(
        "LIGHTRAG_WORKING_DIR",
        r"d:/yuki/LightRAG/existing_lightrag_storage",
    )

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_BINDING_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL") or os.environ.get("LLM_BINDING_HOST")
    if not api_key:
        raise RuntimeError(
            "Missing API key: set OPENAI_API_KEY or LLM_BINDING_API_KEY in environment."
        )

    # Check if previous LightRAG instance exists
    if os.path.exists(lightrag_working_dir) and os.listdir(lightrag_working_dir):
        print("✅ Found existing LightRAG instance, loading...")
    else:
        print("❌ No existing LightRAG instance found, will create new one")

    # Create/Load LightRAG instance with your configurations
    # Resolve embedding configuration from environment with sane defaults
    embed_dim = int(os.environ.get("EMBED_DIM", "3072"))
    embed_model = os.environ.get("EMBED_MODEL", "text-embedding-3-large")

    lightrag_instance = LightRAG(
        working_dir=lightrag_working_dir,
        llm_model_func=lambda prompt, system_prompt=None, history_messages=[], **kwargs: openai_complete_if_cache(
            "deepseek-ai/DeepSeek-V3.1-Terminus",
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            api_key=api_key,
            base_url=base_url,
            **kwargs,
        ),
        embedding_func=EmbeddingFunc(
            embedding_dim=embed_dim,
            func=lambda texts: openai_embed(
                texts,
                model=embed_model,
                api_key=api_key,
                base_url=base_url,
            ),
        ),
    )

    # Initialize storage (this will load existing data if available)
    await lightrag_instance.initialize_storages()
    # Initialize pipeline status required by ingestion pipeline
    await initialize_pipeline_status()

    # Now initialize RAGAnything with the existing LightRAG instance
    rag = RAGAnything(
        lightrag=lightrag_instance,  # Pass the existing LightRAG instance
        # Only need vision model for multimodal processing
        vision_model_func=lambda prompt, system_prompt=None, history_messages=[], image_data=None, **kwargs: (
            openai_complete_if_cache(
                "gpt-4o",
                "",
                system_prompt=None,
                history_messages=[],
                messages=[
                    (
                        {"role": "system", "content": system_prompt}
                        if system_prompt
                        else None
                    ),
                    (
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{image_data}"},
                                },
                            ],
                        }
                        if image_data
                        else {"role": "user", "content": prompt}
                    ),
                ],
                api_key=api_key,
                base_url=base_url,
                **kwargs,
            )
            if image_data
            else openai_complete_if_cache(
                "deepseek-ai/DeepSeek-V3.1-Terminus",
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                api_key=api_key,
                base_url=base_url,
                **kwargs,
            )
        ),
        # Note: working_dir, llm_model_func, embedding_func, etc. are inherited from lightrag_instance
    )

    # Query the existing knowledge base (use plain async text query to avoid nested loops)
    try:
        result = await rag.aquery(
            "What data has been processed in this LightRAG instance?", mode="hybrid"
        )
        print("Query result:", result)
    except Exception as e:
        print("Query failed:", e)
        return

    # Add PDFs from specified directory to the existing LightRAG instance
    # Ingest PDFs from configured import dir, default to working_dir if not set
    pdf_dir = os.environ.get("DEFAULT_IMPORT_DIR", lightrag_working_dir)
    if os.path.isdir(pdf_dir):
        pdf_files = [
            os.path.join(pdf_dir, f)
            for f in os.listdir(pdf_dir)
            if f.lower().endswith(".pdf")
        ]
        if not pdf_files:
            print(f"No PDF files found in {pdf_dir}")
        else:
            print(f"Found {len(pdf_files)} PDF(s) in {pdf_dir}, starting ingestion...")
            for pdf in pdf_files:
                try:
                    print(f"Processing: {pdf}")
                    await rag.process_document_complete(file_path=pdf, output_dir="./output")
                except Exception as e:
                    print(f"Failed to process {pdf}: {e}")
            # Re-run a query after ingestion to check context
            try:
                result_after = await rag.aquery(
                    "Summarize the documents that were ingested.", mode="hybrid"
                )
                print("Post-ingestion query:", result_after)
            except Exception as e:
                print("Post-ingestion query failed:", e)
    else:
        print(f"Directory not found: {pdf_dir}")


if __name__ == "__main__":
    asyncio.run(load_existing_lightrag())

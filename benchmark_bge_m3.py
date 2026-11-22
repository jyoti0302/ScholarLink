
import time
import torch
from FlagEmbedding import BGEM3FlagModel

MODEL_NAME = "BAAI/bge-m3"

print("GPU:", torch.cuda.get_device_name(0))
print("Loading BGE-M3...")

start = time.time()

model = BGEM3FlagModel(
    MODEL_NAME,
    use_fp16=True
)

print(f"Model loading time: {time.time() - start:.2f} seconds")

texts = [
    "Machine learning applications in mining engineering and mineral processing.",
    "Deep learning methods for slope stability prediction and landslide detection.",
    "Artificial intelligence for healthcare diagnosis using medical images.",
    "Natural language processing and retrieval augmented generation systems.",
] * 25  # 100 texts

torch.cuda.reset_peak_memory_stats()
torch.cuda.synchronize()

start = time.time()

embeddings = model.encode(
    texts,
    batch_size=4,
    max_length=512,
    return_dense=True,
    return_sparse=True
)

torch.cuda.synchronize()
elapsed = time.time() - start

print("\n--- BENCHMARK RESULTS ---")
print("Texts processed:", len(texts))
print("Time taken:", round(elapsed, 2), "seconds")
print("Texts per second:", round(len(texts) / elapsed, 2))
print("Texts per minute:", round(len(texts) / elapsed * 60, 2))
print(
    "Peak GPU memory:",
    round(torch.cuda.max_memory_allocated() / (1024 ** 3), 2),
    "GB"
)
print("Dense vector dimension:", len(embeddings["dense_vecs"][0]))
print("Sparse vectors generated:", len(embeddings["lexical_weights"]))

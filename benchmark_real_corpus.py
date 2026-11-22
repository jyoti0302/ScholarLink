
import json
import time
import gc
from pathlib import Path

import torch
from FlagEmbedding import BGEM3FlagModel


# ==========================================
# CONFIGURATION
# ==========================================

DATA_FILE = Path(
    r"C:\Users\jyoti\OneDrive\MTP_2\data\full_corpus\full_corpus_remaining_texts.jsonl"
)

MODEL_NAME = "BAAI/bge-m3"

SAMPLE_SIZE = 120
BATCH_SIZES = [4, 8, 16]
MAX_LENGTH = 512


# ==========================================
# STEP 1: CHECK GPU
# ==========================================

if not torch.cuda.is_available():
    raise RuntimeError("CUDA GPU is not available!")

print("=" * 55)
print("BGE-M3 REAL CORPUS BENCHMARK")
print("=" * 55)

print("GPU:", torch.cuda.get_device_name(0))
print("GPU memory:", round(
    torch.cuda.get_device_properties(0).total_memory / (1024 ** 3), 2
), "GB")


# ==========================================
# STEP 2: LOAD ACTUAL CORPUS
# ==========================================

print("\nReading corpus:", DATA_FILE)

if not DATA_FILE.exists():
    raise FileNotFoundError(
        f"Corpus file not found: {DATA_FILE}"
    )

records = []

with DATA_FILE.open("r", encoding="utf-8") as file:
    for line_number, line in enumerate(file, start=1):

        if not line.strip():
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Invalid JSON on line {line_number}: {error}"
            )

        text = record.get("text_content")

        if isinstance(text, str) and text.strip():
            records.append(record)

print("Valid documents:", len(records))

if len(records) < SAMPLE_SIZE:
    raise ValueError(
        f"Need at least {SAMPLE_SIZE} valid documents."
    )


# ==========================================
# STEP 3: SELECT REPRESENTATIVE DOCUMENTS
# ==========================================

print("\nSelecting representative documents...")

# Sort by text length so the sample covers short,
# medium and long documents.

records.sort(
    key=lambda record: len(record["text_content"])
)

indices = [
    round(
        i * (len(records) - 1) / (SAMPLE_SIZE - 1)
    )
    for i in range(SAMPLE_SIZE)
]

texts = [
    records[index]["text_content"]
    for index in indices
]

lengths = [len(text) for text in texts]

print("Sample size:", len(texts))
print("Shortest document:", min(lengths), "characters")
print("Longest document:", max(lengths), "characters")
print("Average length:", round(sum(lengths) / len(lengths)))


# ==========================================
# STEP 4: LOAD BGE-M3
# ==========================================

print("\nLoading BGE-M3 model...")
print("This may take a few minutes on the first run.")

load_start = time.time()

model = BGEM3FlagModel(
    MODEL_NAME,
    use_fp16=True
)

model_load_time = time.time() - load_start

print(
    "Model loading time:",
    round(model_load_time, 2),
    "seconds"
)


# ==========================================
# STEP 5: TEST DIFFERENT BATCH SIZES
# ==========================================

results = []

for batch_size in BATCH_SIZES:

    print("\n" + "=" * 55)
    print("TESTING BATCH SIZE:", batch_size)
    print("=" * 55)

    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize()

    start_time = time.time()

    try:

        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            max_length=MAX_LENGTH,
            return_dense=True,
            return_sparse=True
        )

        torch.cuda.synchronize()

        elapsed = time.time() - start_time

        texts_per_second = len(texts) / elapsed
        texts_per_minute = texts_per_second * 60

        peak_memory = (
            torch.cuda.max_memory_allocated()
            / (1024 ** 3)
        )

        result = {
            "batch_size": batch_size,
            "documents": len(texts),
            "time_seconds": round(elapsed, 2),
            "texts_per_second": round(texts_per_second, 2),
            "texts_per_minute": round(texts_per_minute, 2),
            "peak_gpu_memory_gb": round(peak_memory, 2),
            "dense_dimension": len(
                embeddings["dense_vecs"][0]
            ),
            "sparse_vectors": len(
                embeddings["lexical_weights"]
            )
        }

        results.append(result)

        print("\nRESULT:")
        for key, value in result.items():
            print(f"{key}: {value}")

        del embeddings

    except torch.cuda.OutOfMemoryError:

        print(
            f"\nGPU OUT OF MEMORY at batch size {batch_size}"
        )

        gc.collect()
        torch.cuda.empty_cache()

        results.append({
            "batch_size": batch_size,
            "error": "CUDA Out Of Memory"
        })

    except Exception as error:

        print("\nERROR:", repr(error))

        gc.collect()
        torch.cuda.empty_cache()

        results.append({
            "batch_size": batch_size,
            "error": repr(error)
        })


# ==========================================
# STEP 6: DISPLAY FINAL RESULTS
# ==========================================

print("\n")
print("=" * 65)
print("FINAL BENCHMARK RESULTS")
print("=" * 65)

for result in results:
    print(json.dumps(result, indent=2))


# ==========================================
# STEP 7: SAVE RESULTS
# ==========================================

output_file = Path(
    "real_corpus_benchmark_results.json"
)

with output_file.open("w", encoding="utf-8") as file:
    json.dump(
        {
            "gpu": torch.cuda.get_device_name(0),
            "model": MODEL_NAME,
            "max_length": MAX_LENGTH,
            "sample_size": SAMPLE_SIZE,
            "model_load_seconds": round(model_load_time, 2),
            "results": results
        },
        file,
        indent=4
    )

print("\nResults saved to:", output_file.resolve())
print("\nBenchmark completed!")

import sys, time
from llama_cpp import Llama

model_path = r'D:\Projects\offline document extraction\models\small\Phi-3-mini-4k-instruct-q4.gguf'
llm = Llama(model_path=model_path, n_ctx=2048, n_threads=4, n_gpu_layers=20, verbose=False)

paper_sample = """Smart Intelligence-Based Emergency Ward Rush Prediction Using Deep Feature Swarm Intelligence with LSTM Gated Hyper Capsule RNN
Balaji M1, Nathiya N2
Abstract: The advancement of healthcare sectors is crucial for providing prompt care. In this paper, we propose an emergency ward rush prediction model combining Deep Feature Swarm Intelligence and LSTM RNN. Experimental results achieve 98.4% accuracy."""

prompt = f"""<|user|>
Extract structured document intelligence from the text below:
{paper_sample}

Return ONLY a JSON object with:
{{
  "title": "Title of the work",
  "authors": ["List of authors or null"],
  "year": "Publication or release year or null",
  "concept": "Core concept or project summary",
  "highlights": ["Key highlight or finding 1", "Key highlight 2"]
}}
<|end|>
<|assistant|>
"""

print('Generating...')
sys.stdout.flush()
t0 = time.time()
res = llm(prompt, max_tokens=512, temperature=0.0)
print('Done in:', time.time() - t0)
print('OUTPUT:\n', res['choices'][0]['text'])

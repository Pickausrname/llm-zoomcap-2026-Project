# Activity Log — "Reviewed code and memory" → "Completed: Create empty `__init__.py` files for `src` and `src/db` (1/4)"

**Scope of this document:** A full, unabridged reconstruction of the assistant's process for the opening segment of Turn 1 of the session — starting at the very first action ("Reviewed code and memory") and ending at the completion of progress-tracker item **1/4**, *"Create empty `__init__.py` files for `src` and `src/db`"*. Every tool call is reproduced with its exact parameters and its exact raw result, including all content that the chat UI collapses behind expandable/"hide details" sections. Nothing is summarized or omitted.

**Task being worked on during this segment:** Implement `src/db/knowledge_store.py` for the MOSFET Selection RAG application, strictly per the attached `SPEC.MD`.

---

## Progress checklist (as tracked during this phase)

- [x] **1/4 — Create empty `__init__.py` files for `src` and `src/db`** ← this document ends here
- [ ] 2/4 — Create `src/config.py` (central path configuration)
- [ ] 3/4 — Create `src/db/knowledge_store.py` (schema + connection management)
- [ ] 4/4 — Add `requirements.txt` and verify the implementation end-to-end

---

## 1. "Reviewed code and memory"

**Rationale:** Before writing any code, check whether prior session/repo memory exists, and confirm the actual on-disk state of the workspace — this matters because the requested file (`knowledge_store.py`) is required by the task to `import KNOWLEDGE_DB from src.config`, so the assistant needed to know whether `src/config.py` already existed.

Two read-only tools were invoked **in parallel** (independent, no data dependency between them):

### Tool call 1 of 2 — `memory`

**Parameters:**
```json
{
  "command": "view",
  "path": "/memories"
}
```

**Raw result:**
```
No memories found.
```

### Tool call 2 of 2 — `list_dir`

**Parameters:**
```json
{
  "path": "c:\\Users\\Tanj\\Documents\\llmzoomcamp2026\\Project\\code"
}
```

**Raw result:**
```
Folder is empty
```

**Conclusion drawn from this step:** No prior memory existed, and the workspace folder was completely empty — no `src/` tree, no `config.py`, nothing. This confirmed that in order to deliver a working `knowledge_store.py`, the assistant would also need to create the minimal supporting scaffolding (`src/__init__.py`, `src/db/__init__.py`, and `src/config.py`) that the spec's project structure and the task's own import constraint required, since none of it existed yet.

---

## 2. Researching exact library APIs before writing code

**Rationale:** The task had two load-bearing technical details that the assistant did not want to guess at: (1) the exact Python API shape for loading the `sqlite-vec` extension and the SQL syntax for `vec0` virtual tables, and (2) the output embedding dimensionality of `sentence-transformers/multi-qa-MiniLM-L6-cos-v1`, which fixes the width of the `master_vec` vector column. Two `fetch_webpage` calls were issued in parallel.

### Tool call 1 of 2 — `fetch_webpage`

**Parameters:**
```json
{
  "query": "sqlite-vec python usage enable_load_extension sqlite_vec.load vec0 virtual table create",
  "urls": [
    "https://github.com/asg017/sqlite-vec/blob/main/README.md",
    "https://raw.githubusercontent.com/asg017/sqlite-vec/main/bindings/python/README.md"
  ]
}
```

**Raw result:**

````text
Here is some relevant context from the web page https://github.com/asg017/sqlite-vec/blob/main/README.md:
...

## Navigation Menu

  [Homepage](https://github.com/)[Sign in](https://github.com/login?return_to=https%3A%2F%2Fgithub.com%2Fasg017%2Fsqlite-vec%2Fblob%2Fmain%2FREADME.md)   [asg017](https://github.com/asg017)/[sqlite-vec](https://github.com/asg017/sqlite-vec)Public 
[You must be signed in to change notification settings](https://github.com/login?return_to=%2Fasg017%2Fsqlite-vec)
[Fork 349](https://github.com/login?return_to=%2Fasg017%2Fsqlite-vec)
[You must be signed in to star a repository](https://github.com/login?return_to=%2Fasg017%2Fsqlite-vec)

       
## 

 main 
 ...
...
# README.md

  
## Latest commit

[asg017](https://github.com/asg017)[commits by asg017](https://github.com/asg017/sqlite-vec/commits?author=asg017)[sponsor update](https://github.com/asg017/sqlite-vec/commit/d1d1ed7a57acba0e74c7ffcb86b3af786af59d22)[Commit d1d1ed7](https://github.com/asg017/sqlite-vec/commit/d1d1ed7a57acba0e74c7ffcb86b3af786af59d22) ·  last year
## History

[View commit history for this file.](https://github.com/asg017/sqlite-vec/commits/main/README.md)  160 lines (130 loc) · 9.17 KB  
...
...
# README.md
...
## File metadata and controls


Preview
Code
Blame

 [Raw](https://github.com/asg017/sqlite-vec/raw/refs/heads/main/README.md)       
...
...
# README.md

  
## Latest commit
...
## History
...
## File metadata and controls
...
...
# `sqlite-vec`
...
## Installing

Permalink: Installing
See [Installing sqlite-vec](https://alexgarcia.xyz/sqlite-vec/installation.html) for more details.


|  |
|  |
| Python | pip install sqlite-vec | sqlite-vec with Python | PyPI |
| Node.js | npm install sqlite-vec | sqlite-vec with Node.js | npm |
| Ruby | gem install sqlite-vec | sqlite-vec with Ruby | Gem |
| Go | go get -u github.com/asg017/sqlite-vec/bindings/go | sqlite-vec with Go | Go Reference |
| Rust | cargo add sqlite-vec | sqlite-vec with Rust | Crates.io |
| Datasette | datasette install datasette-sqlite-vec | sqlite-vec with Datasette | Datasette |
| rqlite | rqlited -extensions-path=sqlite-vec.tar.gz | sqlite-vec with rqlite | rqlite |
...
...
# `sqlite-vec`
...
## Installing
...
| sqlite-utils | sqlite-utils install sqlite-utils-sqlite-vec | sqlite-vec with sqlite-utils | sqlite-utils |
| Github Release |   |   | GitHub tag (latest SemVer pre-release) |
...
...
# `sqlite-vec`
...
## Sample usage

Permalink: Sample usage  .load ./vec0

create virtual table vec_examples using vec0(
  sample_embedding float[8]
);

-- vectors can be provided as JSON or in a compact binary format
insert into vec_examples(rowid, sample_embedding)
  values
    (1, '[-0.200, 0.250, 0.341, -0.211, 0.645, 0.935, -0.316, -0.924]'),
    (2, '[0.443, -0.501, 0.355, -0.771, 0.707, -0.708, -0.185, 0.362]'),
    (3, '[0.716, -0.927, 0.134, 0.052, -0.669, 0.793, -0.634, -0.162]'),
...
...
# `sqlite-vec`
...
## Sample usage
...
    (4, '[-0.710, 0.330, 0.656, 0.041, -0.990, 0.726, 0.385, -0.958]');


-- KNN style query
select
  rowid,
  distance
from vec_examples
where sample_embedding match '[0.890, 0.544, 0.825, 0.961, 0.358, 0.0196, 0.521, 0.175]'
order by distance
limit 2;
/*
┌───────┬──────────────────┐
│ rowid │     distance     │
├───────┼──────────────────┤
│ 2     │ 2.38687372207642 │
│ 1     │ 2.38978505134583 │
└───────┴──────────────────┘
*/ 
...
...
# `sqlite-vec`
...
## Sponsors

Permalink: Sponsors
Development of `sqlite-vec` is supported by multiple generous sponsors! Mozilla is the main sponsor through
the new Builders project.


[Mozilla Builders logo](https://hacks.mozilla.org/2024/06/sponsoring-sqlite-vec-to-enable-more-powerful-local-ai-applications/)


`sqlite-vec` is also sponsored by the following companies:

[Fly.io logo](https://fly.io/)[Turso logo](https://tur.so/sqlite-vec)[SQLite Cloud logo](https://sqlitecloud.io/)[Shinkai logo](https://shinkai.com/)
As well as multiple individual supporters on [Github sponsors](https://github.com/sponsors/asg017/)!


If your company interested in sponsoring `sqlite-vec` development, send me an email to get more info: [https://alexgarcia.xyz](https://alexgarcia.xyz/)

 
...
...
# `sqlite-vec`
...
## See Also

Permalink: See Also
• [sqlite-ecosystem](https://github.com/asg017/sqlite-ecosystem), Maybe more 3rd party SQLite extensions I've developed
• [sqlite-rembed](https://github.com/asg017/sqlite-rembed), Generate text embeddings from remote APIs like OpenAI/Nomic/Ollama, meant for
testing and SQL scripts
• [sqlite-lembed](https://github.com/asg017/sqlite-lembed), Generate text embeddings locally from embedding models in the `.gguf` format

     

...
...
# `sqlite-vec`
...
## Additional Links
- [Code](https://github.com/asg017/sqlite-vec)
- [Issues 155](https://github.com/asg017/sqlite-vec/issues)
- [Pull requests 47](https://github.com/asg017/sqlite-vec/pulls)
- [Actions](https://github.com/asg017/sqlite-vec/actions)
- [Projects](https://github.com/asg017/sqlite-vec/projects)
- [sqlite-vec](https://github.com/asg017/sqlite-vec/tree/main)
...
# `sqlite-vec`

Permalink: sqlite-vec
[](https://discord.gg/Ve7WeCJFXk)


An extremely small, "fast enough" vector search SQLite extension that runs
anywhere! A successor to [sqlite-vss](https://github.com/asg017/sqlite-vss)

Important
`sqlite-vec` is a pre-v1, so expect breaking changes!


• Store and query float, int8, and binary vectors in `vec0` virtual tables
• Written in pure C, no dependencies, runs anywhere SQLite runs
(Linux/MacOS/Windows, in the browser with WASM, Raspberry Pis, etc.)
• Store non-vector data in metadata, auxiliary, or partition key columns


[Mozilla Builders logo](https://hacks.mozilla.org/2024/06/sponsoring-sqlite-vec-to-enable-more-powerful-local-ai-applications/)
...
...
# `sqlite-vec`
...
`sqlite-vec` is a [Mozilla Builders project](https://hacks.mozilla.org/2024/06/sponsoring-sqlite-vec-to-enable-more-powerful-local-ai-applications/), with additional sponsorship from [ Fly.io ](https://fly.io/), [ Turso](https://tur.so/sqlite-vec), [ SQLite Cloud](https://sqlitecloud.io/), and [ Shinkai](https://shinkai.com/). See the Sponsors section for more details.

 
## Installing
...
## Sample usage
...
## Sponsors
...
## See Also
...
## Additional Links
...
  Skip to content  
## Navigation Menu
...
## 
 ...
# README.md
...
# `sqlite-vec`
...
Here is some relevant context from the web page https://raw.githubusercontent.com/asg017/sqlite-vec/main/bindings/python/README.md:
An error occurred retrieving the fetch result: HTTP error 404
````

### Tool call 2 of 2 — `fetch_webpage`

**Parameters:**
```json
{
  "query": "embedding dimension output size multi-qa-MiniLM-L6-cos-v1",
  "urls": ["https://huggingface.co/sentence-transformers/multi-qa-MiniLM-L6-cos-v1"]
}
```

**Raw result:**

````text
Here is some relevant context from the web page https://huggingface.co/sentence-transformers/multi-qa-MiniLM-L6-cos-v1:
...
#  [](https://huggingface.co/sentence-transformers)[sentence-transformers](https://huggingface.co/sentence-transformers) / multi-qa-MiniLM-L6-cos-v1like138 FollowSentence Transformers5.84k

[Sentence Similarity](https://huggingface.co/models?pipeline_tag=sentence-similarity)[sentence-transformers](https://huggingface.co/models?library=sentence-transformers)[PyTorch](https://huggingface.co/models?library=pytorch)[TensorFlow](https://huggingface.co/models?library=tf)[ONNX](https://huggingface.co/models?library=onnx)[Safetensors](https://huggingface.co/models?library=safetensors)[OpenVINO](https://huggingface.co/models?library=openvino)[Transformers](https://huggingface.co/models?library=transformers)12 datasets[English](https://huggingface.co/models?language=en)[bert](https://huggingface.co/models?other=bert)[feature-ext...
...
# multi-qa-MiniLM-L6-cos-v1
...
## Usage (Sentence-Transformers)


Using this model becomes easy when you have [sentence-transformers](https://www.sbert.net/) installed:

  
```
pip install -U sentence-transformers

```

Then you can use the model like this:

  
```
from sentence_transformers import SentenceTransformer, util

query = "How many people live in London?"
docs = ["Around 9 Million people live in London", "London is known for its financial district"]

#Load the model
model = SentenceTransformer('sentence-transformers/multi-qa-MiniLM-L6-cos-v1')

#Encode query and documents
query_emb = model.encode(query)
doc_emb = model.encode(docs)

#Compute dot score between query and all document embeddings
scores = util.dot_score(query_emb, doc_emb)[0].cpu().tolist()

#Combine docs & scores
doc_score_pairs = list(zip(docs, scores))

#Sort by decreasing score
...
...
# multi-qa-MiniLM-L6-cos-v1
...
## Usage (Sentence-Transformers)
...
doc_score_pairs = sorted(doc_score_pairs, key=lambda x: x[1], reverse=True)

#Output passages & scores
for doc, score in doc_score_pairs:
    print(score, doc)

```
...
...
# multi-qa-MiniLM-L6-cos-v1
...
## PyTorch Usage (HuggingFace Transformers)


Without [sentence-transformers](https://www.sbert.net/), you can use the model like this: First, you pass your input through the
transformer model, then you have to apply the correct pooling-operation on-top of the
contextualized word embeddings.

  
```
from transformers import AutoTokenizer, AutoModel
import torch
import torch.nn.functional as F

#Mean Pooling - Take average of all tokens
def mean_pooling(model_output, attention_mask):
    token_embeddings = model_output.last_hidden_state
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)


#Encode text
def encode(texts):
    # Tokenize sentences
    encoded_input = tokenizer(texts, padding=True, truncation=True, return_tensors='pt')
...
...
# multi-qa-MiniLM-L6-cos-v1
...
## PyTorch Usage (HuggingFace Transformers)
...
    # Compute token embeddings
    with torch.no_grad():
        model_output = model(**encoded_input, return_dict=True)

    # Perform pooling
    embeddings = mean_pooling(model_output, encoded_input['attention_mask'])

    # Normalize embeddings
    embeddings = F.normalize(embeddings, p=2, dim=1)
    
    return embeddings


# Sentences we want sentence embeddings for
query = "How many people live in London?"
docs = ["Around 9 Million people live in London", "London is known for its financial district"]

# Load model from HuggingFace Hub
tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/multi-qa-MiniLM-L6-cos-v1")
model = AutoModel.from_pretrained("sentence-transformers/multi-qa-MiniLM-L6-cos-v1")

#Encode query and docs
query_emb = encode(query)
doc_emb = encode(docs)
...
...
# multi-qa-MiniLM-L6-cos-v1
...
## PyTorch Usage (HuggingFace Transformers)
...
#Compute dot score between query and all document embeddings
scores = torch.mm(query_emb, doc_emb.transpose(0, 1))[0].cpu().tolist()

#Combine docs & scores
doc_score_pairs = list(zip(docs, scores))

#Sort by decreasing score
doc_score_pairs = sorted(doc_score_pairs, key=lambda x: x[1], reverse=True)

#Output passages & scores
for doc, score in doc_score_pairs:
    print(score, doc)

```
...
...
# multi-qa-MiniLM-L6-cos-v1
...
## TensorFlow Usage (HuggingFace Transformers)


Similarly to the PyTorch example above, to use the model with TensorFlow you
pass your input through the transformer model, then you have to apply the correct
pooling-operation on-top of the contextualized word embeddings.

  
```
from transformers import AutoTokenizer, TFAutoModel
import tensorflow as tf

#Mean Pooling - Take attention mask into account for correct averaging
def mean_pooling(model_output, attention_mask):
    token_embeddings = model_output.last_hidden_state
    input_mask_expanded = tf.cast(tf.tile(tf.expand_dims(attention_mask, -1), [1, 1, token_embeddings.shape[-1]]), tf.float32)
    return tf.math.reduce_sum(token_embeddings * input_mask_expanded, 1) / tf.math.maximum(tf.math.reduce_sum(input_mask_expanded, 1), 1e-9)


#Encode text
def encode(texts):
    # Tokenize sentences
...
...
# multi-qa-MiniLM-L6-cos-v1
...
## TensorFlow Usage (HuggingFace Transformers)
...
    encoded_input = tokenizer(texts, padding=True, truncation=True, return_tensors='tf')

    # Compute token embeddings
    model_output = model(**encoded_input, return_dict=True)

    # Perform pooling
    embeddings = mean_pooling(model_output, encoded_input['attention_mask'])

    # Normalize embeddings
    embeddings = tf.math.l2_normalize(embeddings, axis=1)

    return embeddings


# Sentences we want sentence embeddings for
query = "How many people live in London?"
docs = ["Around 9 Million people live in London", "London is known for its financial district"]

# Load model from HuggingFace Hub
tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/multi-qa-MiniLM-L6-cos-v1")
model = TFAutoModel.from_pretrained("sentence-transformers/multi-qa-MiniLM-L6-cos-v1")

#Encode query and docs
...
...
# multi-qa-MiniLM-L6-cos-v1
...
## TensorFlow Usage (HuggingFace Transformers)
...
query_emb = encode(query)
doc_emb = encode(docs)

#Compute dot score between query and all document embeddings
scores = (query_emb @ tf.transpose(doc_emb))[0].numpy().tolist()

#Combine docs & scores
doc_score_pairs = list(zip(docs, scores))

#Sort by decreasing score
doc_score_pairs = sorted(doc_score_pairs, key=lambda x: x[1], reverse=True)

#Output passages & scores
for doc, score in doc_score_pairs:
    print(score, doc)

```
...
...
# multi-qa-MiniLM-L6-cos-v1
...
## Technical Details


In the following some technical details how this model must be used:


|  |
|  |
| Dimensions | 384 |
| Produces normalized embeddings | Yes |
| Pooling-Method | Mean pooling |
| Suitable score functions | dot-product (util.dot_score), cosine-similarity (util.cos_sim), or euclidean distance |


Note: When loaded with `sentence-transformers`, this model produces normalized embeddings with length 1. In that case,
dot-product and cosine-similarity are equivalent. dot-product is preferred as it is
faster. Euclidean distance is proportional to dot-product and can also be used.


...
...
# multi-qa-MiniLM-L6-cos-v1
...
## Background


The project aims to train sentence embedding models on very large sentence level
datasets using a self-supervised contrastive learning objective. We use a
contrastive learning objective: given a sentence from the pair, the model should
predict which out of a set of randomly sampled other sentences, was actually paired
with it in our dataset.


We developped this model during the [Community week using JAX/Flax for NLP & CV](https://discuss.huggingface.co/t/open-to-the-community-community-week-using-jax-flax-for-nlp-cv/7104), organized by Hugging Face. We developped this model as part of the project: [Train the Best Sentence Embedding Model Ever with 1B Training Pairs](https://discuss.huggingface.co/t/train-the-best-sentence-embedding-model-ever-with-1b-training-pairs/7354). We benefited from efficient hardware infrastructure to run the project: 7 TPUs
...
...
# multi-qa-MiniLM-L6-cos-v1
...
## Background
...
v3-8, as well as intervention from Googles Flax, JAX, and Cloud team member
about efficient deep learning frameworks.
...
...
# multi-qa-MiniLM-L6-cos-v1
...
## Intended uses


Our model is intented to be used for semantic search: It encodes queries /
questions and text paragraphs in a dense vector space. It finds relevant documents
for the given passages.


Note that there is a limit of 512 word pieces: Text longer than that will be
truncated. Further note that the model was just trained on input text up to 250
word pieces. It might not work well for longer text.


...
...
# multi-qa-MiniLM-L6-cos-v1
...
## Training procedure
...
### Pre-training
...
#### Training


We use the concatenation from multiple datasets to fine-tune our model. In total
we have about 215M (question, answer) pairs. We sampled each dataset given a
weighted probability which configuration is detailed in the `data_config.json` file.


The model was trained with [MultipleNegativesRankingLoss](https://www.sbert.net/docs/package_reference/losses.html#multiplenegativesrankingloss) using Mean-pooling, cosine-similarity as similarity function, and a scale of
20.


|  |
|  |
| WikiAnswers Duplicate question pairs from WikiAnswers | 77,427,422 |
| PAQ Automatically generated (Question, Paragraph) pairs for each paragraph in Wikipedia | 64,371,441 |
| Stack Exchange (Title, Body) pairs from all StackExchanges | 25,316,456 |
...
...
# multi-qa-MiniLM-L6-cos-v1
...
## Training procedure
...
### Pre-training
...
#### Training
...
| Stack Exchange (Title, Answer) pairs from all StackExchanges | 21,396,559 |
| MS MARCO Triplets (query, answer, hard_negative) for 500k queries from Bing search engine | 17,579,773 |
| GOOAQ: Open Question Answering with Diverse Answer Types (query, answer) pairs for 3M Google queries and Google featured snippet | 3,012,496 |
| Amazon-QA (Question, Answer) pairs from Amazon product pages | 2,448,839 |
| Yahoo Answers (Title, Answer) pairs from Yahoo Answers | 1,198,260 |
| Yahoo Answers (Question, Answer) pairs from Yahoo Answers | 681,164 |
| Yahoo Answers (Title, Question) pairs from Yahoo Answers | 659,896 |
...
...
# multi-qa-MiniLM-L6-cos-v1
...
## Training procedure
...
### Pre-training
...
#### Training
...
| SearchQA (Question, Answer) pairs for 140k questions, each with Top5 Google snippets on that question | 582,261 |
| ELI5 (Question, Answer) pairs from Reddit ELI5 (explainlikeimfive) | 325,475 |
| Stack Exchange Duplicate questions pairs (titles) | 304,525 |
| Quora Question Triplets (Question, Duplicate_Question, Hard_Negative) triplets for Quora Questions Pairs dataset | 103,663 |
| Natural Questions (NQ) (Question, Paragraph) pairs for 100k real Google queries with relevant Wikipedia paragraph | 100,231 |
| SQuAD2.0 (Question, Paragraph) pairs from SQuAD2.0 dataset | 87,599 |
| TriviaQA (Question, Evidence) pairs | 73,346 |
| Total | 214,988,242 |
...
...
# multi-qa-MiniLM-L6-cos-v1
...
## Training procedure
...
### Pre-training
...
#### Training
...
- **Downloads last month** 955,751

[Image: Image]

  Safetensors[](https://huggingface.co/docs/safetensors) Model size 22.7M params Tensor typeI64 ·F32 
Files info

  Inference Providers[NEW](https://huggingface.co/docs/inference-providers) [Sentence Similarity](https://huggingface.co/tasks/sentence-similarity)  ExamplesSource Sentence Sentences to compare to  Add SentenceGenerate View CodeMaximize
...
...
# multi-qa-MiniLM-L6-cos-v1
...
## Training procedure
...
### Pre-training


We use the pretrained [nreimers/MiniLM-L6-H384-uncased](https://huggingface.co/nreimers/MiniLM-L6-H384-uncased) model. Please refer to the model card for more detailed information about the
pre-training procedure.


#### Training
...
...
# multi-qa-MiniLM-L6-cos-v1
...
## Training procedure


The full training script is accessible in this current repository: `train_script.py`.


### Pre-training
...
...
# multi-qa-MiniLM-L6-cos-v1
...
## Model tree forsentence-transformers/multi-qa-MiniLM-L6-cos-v1

  [Image: Image]

 Adapters[1 model](https://huggingface.co/models?other=base_model:adapter:sentence-transformers/multi-qa-MiniLM-L6-cos-v1)  [Image: Image]

 Finetunes[27 models](https://huggingface.co/models?other=base_model:finetune:sentence-transformers/multi-qa-MiniLM-L6-cos-v1)  [Image: Image]

 Quantizations[4 models](https://huggingface.co/models?other=base_model:quantized:sentence-transformers/multi-qa-MiniLM-L6-cos-v1)
## Datasets used to trainsentence-transformers/multi-qa-MiniLM-L6-cos-v1


## Spaces usingsentence-transformers/multi-qa-MiniLM-L6-cos-v1100

      
...
...
# multi-qa-MiniLM-L6-cos-v1
...
## Run 15,000+ Models Instantly


Inference Providers let you run inference on thousands of models served by our
partners using a simple, unified, OpenAI-compatible serverless API ([Learn more](https://huggingface.co/docs/inference-providers)).


sentence-transformers/multi-qa-MiniLM-L6-cos-v1 is supported by the following Inference Providers:

HF Inference APIView API CodeDismiss

...
...
# multi-qa-MiniLM-L6-cos-v1
...
## Additional Links
- [Viewer • Updated Jan 5, 2024 • 914k • 86.5k • 199](https://huggingface.co/datasets/mandarjoshi/trivia_qa)
- [Updated Jan 11, 2024 • 35.2k • 52](https://huggingface.co/datasets/defunct-datasets/eli5)
- [Viewer • Updated Mar 11, 2024 • 26.3k • 22k • 127](https://huggingface.co/datasets/google-research-datasets/natural_questions)
- [📊 mteb/leaderboard](https://huggingface.co/spaces/mteb/leaderboard)
- [🥇 mteb/leaderboard_legacy](https://huggingface.co/spaces/mteb/leaderboard_legacy)
...
...
# multi-qa-MiniLM-L6-cos-v1
...
## Additional Links
...
- [🥇 sq66/leaderboard_legacy](https://huggingface.co/spaces/sq66/leaderboard_legacy)
- [⚡ naveenus/yt-productivity-scorer](https://huggingface.co/spaces/naveenus/yt-productivity-scorer)
- [🥇 shiwan7788/leaderboard-uni](https://huggingface.co/spaces/shiwan7788/leaderboard-uni)
- [⚡ duguaynins/Server](https://huggingface.co/spaces/duguaynins/Server)
- [🧐 📄 🇨🇴 jorge-henao/ask2democracycol](https://huggingface.co/spaces/jorge-henao/ask2democracycol)
...
...
# multi-qa-MiniLM-L6-cos-v1
...
## Additional Links
...
- [📚 Abhilashvj/haystack_QA](https://huggingface.co/spaces/Abhilashvj/haystack_QA)
- [TOS](https://huggingface.co/terms-of-service)
- [Privacy](https://huggingface.co/privacy)
- [About](https://huggingface.co/huggingface)
- [Careers](https://apply.workable.com/huggingface/)
- [Hugging Face](https://huggingface.co/)
- [Models](https://huggingface.co/models)
- [Datasets](https://huggingface.co/datasets)
- [Spaces](https://huggingface.co/spaces)
- [Pricing](https://huggingface.co/pricing)
- [Docs](https://huggingface.co/docs)
...
# multi-qa-MiniLM-L6-cos-v1


This is a [sentence-transformers](https://www.sbert.net/) model: It maps sentences & paragraphs to a 384 dimensional dense vector space
and was designed for semantic search. It has been trained on 215M (question, answer) pairs from diverse sources. For
an introduction to semantic search, have a look at: [SBERT.net - Semantic Search](https://www.sbert.net/examples/applications/semantic-search/README.html)


## Usage (Sentence-Transformers)
...
## PyTorch Usage (HuggingFace Transformers)
...
## TensorFlow Usage (HuggingFace Transformers)
...
## Technical Details
...
## Background
...
## Intended uses
...
## Training procedure
...
## Model tree forsentence-transformers/multi-qa-MiniLM-L6-cos-v1
 ...
## Datasets used to trainsentence-transformers/multi-qa-MiniLM-L6-cos-v1
...
...
# multi-qa-MiniLM-L6-cos-v1
...
## Spaces usingsentence-transformers/multi-qa-MiniLM-L6-cos-v1100

      
## Run 15,000+ Models Instantly
...
## Additional Links
...
    [Hugging Face's logo Hugging Face](https://huggingface.co/)     
#  [](https://huggingface.co/sentence-transformers)[sentence-transformers](https://huggingface.co/sentence-transformers) / multi-qa-MiniLM-L6-cos-v1like138 FollowSentence Transformers5.84k
...
# multi-qa-MiniLM-L6-cos-v1
...
````

**Conclusion drawn from this step:** Confirmed the `vec0` virtual-table SQL syntax (`CREATE VIRTUAL TABLE ... USING vec0(col FLOAT[N])`, rowid-based KNN queries via `MATCH`) and confirmed the embedding model produces **384-dimensional** vectors — both facts were then hard-coded as `EMBEDDING_DIM = 384` and the `master_vec` schema in the eventual `knowledge_store.py`.

---

## 3. Confirming exact, pinnable dependency versions

**Rationale:** The spec mandates that "every package MUST have an exact `==` version in `requirements.txt`." Rather than guess at version numbers, the assistant queried PyPI directly for the two packages needed at this stage (`sqlite-vec`, `python-dotenv`).

### Tool call 1 of 2 — `fetch_webpage`

**Parameters:**
```json
{
  "query": "sqlite-vec latest version release",
  "urls": ["https://pypi.org/project/sqlite-vec/"]
}
```

**Raw result:**

````text
Here is some relevant context from the web page https://pypi.org/project/sqlite-vec/:
...
# sqlite-vec 0.1.9
...
## Project links


[Homepage](https://todo.com/)


## Key dates

PyPI data ›
Released: Mar 31, 2026

 LATEST RELEASE
## 1 maintainer

PyPI data ›[alex.garcia](https://pypi.org/user/alex.garcia/)
## Credits


Author: TODO


## License


MIT License, Apache License, Version 2.0

 Report project as malware 
## Help


## About PyPI


## Contributing to PyPI


...
...
# sqlite-vec 0.1.9
...
## Using PyPI


Status:[ All Systems Operational](https://status.python.org/)


Developed and maintained by the Python community, for the Python community.[Donate today!](https://donate.pypi.org/)


"PyPI", "Python Package Index", and the blocks logos are registered [trademarks](https://pypi.org/trademarks/) of the [Python Software Foundation](https://www.python.org/psf-landing).


© 2026 [Python Software Foundation](https://www.python.org/psf-landing/)[Site map](https://pypi.org/sitemap/)


Deployed from [e7746c4](https://github.com/pypi/warehouse/commit/e7746c42e384aaf9553cad0ca1c056dd67f561b0)

 Switch to desktop version 
English
español
français
日本語
português (Brasil)
українська
...
...
# sqlite-vec 0.1.9
...
## Using PyPI
...
Ελληνικά
Deutsch
中文 (简体)
中文 (繁體)
русский
עברית
Esperanto
한국어

[AWS Cloud computing and Security Sponsor](https://aws.amazon.com/)[Datadog Monitoring](https://www.datadoghq.com/)[Depot Continuous Integration](https://depot.dev/)[Fastly CDN](https://www.fastly.com/)[Google Download Analytics](https://careers.google.com/)[Sentry Error logging](https://sentry.io/for/python/?utm_source=pypi&utm_medium=paid-community&utm_campaign=python-na-evergreen&utm_content=static-ad-pypi-sponsor-learnmore)[StatusPage Status page](https://statuspage.io/)
...
...
# sqlite-vec 0.1.9
...
## Additional Links
- [Installing packages](https://packaging.python.org/tutorials/installing-packages/) - External link
- [Uploading packages](https://packaging.python.org/tutorials/packaging-projects/) - External link
- [User guide](https://packaging.python.org/) - External link
- [Project name retention](https://www.python.org/dev/peps/pep-0541/) - External link
- [FAQs](https://pypi.org/help/)
- [PyPI Blog](https://blog.pypi.org/) - External link
- [Infrastructure dashboard](https://dtdg.co/pypi) - External link
- [Statistics](https://pypi.org/stats/)
- [Logos & trademarks](https://pypi.org/trademarks/)
- [Our sponsors](https://pypi.org/sponsors/)
- [Bugs and feedback](https://pypi.org/help/#feedback)
...
...
# sqlite-vec 0.1.9
...
## Additional Links
...
- [Contribute on GitHub](https://github.com/pypi/warehouse) - External link
- [Translate PyPI](https://hosted.weblate.org/projects/pypa/warehouse/) - External link
- [Sponsor PyPI](https://pypi.org/sponsors/)
- [Development credits](https://github.com/pypi/warehouse/graphs/contributors) - External link
- [Terms of Service](https://policies.python.org/pypi.org/Terms-of-Service/) - External link
- [Report security issue](https://pypi.org/security/)
- [Code of conduct](https://policies.python.org/python.org/code-of-conduct/) - External link
- [Privacy Notice](https://policies.python.org/pypi.org/Privacy-Notice/) - External link
...
...
# sqlite-vec 0.1.9
...
## Additional Links
...
- [Acceptable Use Policy](https://policies.python.org/pypi.org/Acceptable-Use-Policy/) - External link
...
# sqlite-vec 0.1.9

 pip install sqlite-vecCopy PIP instructions
TODO readme


## Project links
...
## Key dates
...
## 1 maintainer
...
## Credits
...
## License
...
## Help


## About PyPI


## Contributing to PyPI


## Using PyPI
...
## Additional Links
...
Skip to main content  [PyPI](https://pypi.org/) Search PyPI Search
# sqlite-vec 0.1.9
...
````

### Tool call 2 of 2 — `fetch_webpage`

**Parameters:**
```json
{
  "query": "python-dotenv latest version release",
  "urls": ["https://pypi.org/project/python-dotenv/"]
}
```

**Raw result:**

````text
Here is some relevant context from the web page https://pypi.org/project/python-dotenv/:
...
# python-dotenv 1.2.3


Read key-value pairs from a .env file and set them as environment variables

 pip install python-dotenvCopy PIP instructions
...
...
# python-dotenv
...
## Getting Started

 pip install python-dotenv

If your application takes its configuration from environment variables, like a
12-factor application, launching it in development is not very practical because
you have to set those environment variables yourself.


To help you with that, you can add python-dotenv to your application to make it
load the configuration from a `.env` file when it is present (e.g. in development) while remaining configurable via
the environment:

 from dotenv import load_dotenv

load_dotenv()  # reads variables from a .env file and sets them in os.environ

...
...
# python-dotenv


[Build Status](https://github.com/theskumar/python-dotenv/actions/workflows/test.yml) [PyPI version](https://badge.fury.io/py/python-dotenv)


python-dotenv reads key-value pairs from a `.env` file and can set them as environment variables. It helps in the development of
applications following the [12-factor](https://12factor.net/) principles.


• Getting Started
• Other Use Cases
  • Load configuration without altering the environment
  • Parse configuration as a stream
  • Load .env files in IPython
• Command-line Interface
• File format
  • Multiline values
  • Variable expansion
• Related Projects
• Acknowledgements


## Getting Started
...
...
# Code of your application, which uses environment variables (e.g. from
`os.environ` or
# `os.getenv`) as if they came from the actual environment.

By default, `load_dotenv()` will:


• Look for a `.env` file in the same directory as the Python script (or higher up the directory
tree).
• Read each key-value pair and add it to `os.environ`.
• Not override existing environment variables (`override=False`). Pass `override=True` to override existing variables.


To configure the development environment, add a `.env` in the root directory of your project:

 
```
.
├── .env
└── foo.py

```

The syntax of `.env` files supported by python-dotenv is similar to that of Bash:

...
...
 # Development settings
...
## Other Use Cases


### Load configuration without altering the environment


The function `dotenv_values` works more or less the same way as `load_dotenv`, except it doesn't touch the environment, it just returns a `dict` with the values parsed from the `.env` file.

 from dotenv import dotenv_values

config = dotenv_values(".env")  # config = {"USER": "foo", "EMAIL": "foo@example.org"}

This notably enables advanced configuration management:

 import os
from dotenv import dotenv_values

config = {
    **dotenv_values(".env.shared"),  # load shared development variables
    **dotenv_values(".env.secret"),  # load sensitive variables
    **os.environ,  # override loaded values with environment variables
}

...
...
 # Development settings
...
## Other Use Cases
...
### Parse configuration as a stream


`load_dotenv` and `dotenv_values` accept [streams](https://docs.python.org/3/library/io.html) via their `stream` argument. It is thus possible to load the variables from sources other than the
filesystem (e.g. the network).

 from io import StringIO

from dotenv import load_dotenv

config = StringIO("USER=foo\nEMAIL=foo@example.org")
load_dotenv(stream=config)

### Load .env files in IPython


You can use dotenv in IPython. By default, it will use `find_dotenv` to search for a `.env` file:

 %load_ext dotenv
%dotenv

You can also specify a path:

 %dotenv relative/or/absolute/path/to/.env

Optional flags:


• `-o` to override existing variables.
• `-v` for increased verbosity.


### Disable load_dotenv


Set `PYTHON_DOTENV_DISABLED=1` to disable `load_dotenv()` from loading .env files or streams. Useful when you can't modify third-party
package calls or in production.


...
...
 # Development settings
...
## Other Use Cases


### Load configuration without altering the environment
...
### Parse configuration as a stream
...
### Load .env files in IPython
...
### Disable load_dotenv
...
...
 # Development settings
...
## Command-line Interface


A CLI interface `dotenv` is also included, which helps you manipulate the `.env` file without manually opening it.

 $ pip install "python-dotenv[cli]"
$ dotenv set USER foo
$ dotenv set EMAIL foo@example.org
$ dotenv list
USER=foo
EMAIL=foo@example.org
$ dotenv list --format=json
{
  "USER": "foo",
  "EMAIL": "foo@example.org"
}
$ dotenv run -- python foo.py

Run `dotenv --help` for more information about the options and subcommands.


...
...
 # Development settings
...
## File format
...
### Multiline values


It is possible for single- or double-quoted values to span multiple lines. The
following examples are equivalent:

 FOO="first line
second line"
 FOO="first line\nsecond line"

### Variable without a value


A variable can have no value:

 FOO

It results in `dotenv_values` associating that variable name with the value `None` (e.g. `{"FOO": None}`. `load_dotenv`, on the other hand, simply ignores such variables.


This shouldn't be confused with `FOO=`, in which case the variable is associated with the empty string.


...
...
 # Development settings
...
## File format
...
### Variable expansion


python-dotenv can interpolate variables using POSIX variable expansion.


With `load_dotenv(override=True)` or `dotenv_values()`, the value of a variable is the first of the values defined in the following
list:


• Value of that variable in the `.env` file.
• Value of that variable in the environment.
• Default value, if provided.
• Empty string.


With `load_dotenv(override=False)`, the value of a variable is the first of the values defined in the following
list:


• Value of that variable in the environment.
• Value of that variable in the `.env` file.
• Default value, if provided.
• Empty string.


...
...
 # Development settings
...
## File format


The format is not formally specified and still improves over time. That being
said, `.env` files should mostly look like Bash files. Reading from FIFOs (named pipes) on
Unix systems is also supported.


Keys can be unquoted or single-quoted. Values can be unquoted, single- or
double-quoted. Spaces before and after keys, equal signs, and values are ignored.
Values can be followed by a comment. Lines can start with the `export` directive, which does not affect their interpretation.


Allowed escape sequences:


• in single-quoted values: `\\`, `\'`
• in double-quoted values: `\\`, `\'`, `\"`, `\a`, `\b`, `\f`, `\n`, `\r`, `\t`, `\v`


### Multiline values
...
### Variable without a value
...
### Variable expansion
...
...
 # Development settings
...
## Related Projects


• [environs](https://github.com/sloria/environs)
• [Honcho](https://github.com/nickstenning/honcho)
• [dump-env](https://github.com/sobolevn/dump-env)
• [dynaconf](https://github.com/dynaconf/dynaconf)
• [parse_it](https://github.com/naorlivne/parse_it)
• [django-dotenv](https://github.com/jpadilla/django-dotenv)
• [django-environ](https://github.com/joke2k/django-environ)
• [python-decouple](https://github.com/HBNetwork/python-decouple)
• [django-configuration](https://github.com/jezdez/django-configurations)


...
...
 # Development settings
...
## Acknowledgements


This project is currently maintained by [Saurabh Kumar](https://saurabh-kumar.com/) and [Bertrand Bonnefoy-Claudet](https://github.com/bbc2) and would not have been possible without the support of these [awesome people](https://github.com/theskumar/python-dotenv/graphs/contributors).


...
...
 # Development settings
DOMAIN=example.org
ADMIN_EMAIL=admin@${DOMAIN}
ROOT_URL=${DOMAIN}/app

If you use variables in values, ensure they are surrounded with `{` and `}`, like `${DOMAIN}`, as bare variables such as `$DOMAIN` are not expanded.


You will probably want to add `.env` to your `.gitignore`, especially if it contains secrets like a password.


See the section "File format" below for more information about what you can write in a `.env` file.


## Other Use Cases
...
## Command-line Interface
...
## File format
...
## Related Projects
...
## Acknowledgements
...
...
# Changelog
...
## [Unreleased](https://github.com/theskumar/python-dotenv/compare/v1.2.3...HEAD)


...
...
# Changelog
...
## [1.2.3](https://github.com/theskumar/python-dotenv/compare/v1.2.2...v1.2.3) - 2026-08-16


### Fixed


• Strip a leading UTF-8 BOM from `.env` file contents so the first variable is no longer silently lost when the file is
saved with BOM (e.g. by some JetBrains IDEs on Windows) by [@h1whelan](https://github.com/h1whelan) in [#640](https://github.com/theskumar/python-dotenv/pull/640)
• `set_key` now escapes backslashes, so values containing them (Windows paths, regular
expressions) survive a write/read round-trip. Quoted values ending in an escaped
backslash are no longer mis-parsed as an escaped quote, which used to swallow the
following lines by [@dchaudhari7177](https://github.com/dchaudhari7177) in [#680](https://github.com/theskumar/python-dotenv/pull/680)
...
...
# Changelog
...
## [1.2.3](https://github.com/theskumar/python-dotenv/compare/v1.2.2...v1.2.3) - 2026-08-16


### Fixed
...
• `dotenv run` now prints a friendly error instead of a traceback when no command is given by [@bbc2](https://github.com/bbc2) in [#606](https://github.com/theskumar/python-dotenv/pull/606)
• Cache the parsed result for empty `.env` files so repeated `dotenv_values`/`load_dotenv` calls no longer re-read the file by [@ReinerBRO](https://github.com/ReinerBRO) in [#638](https://github.com/theskumar/python-dotenv/pull/638)
...
...
# Changelog
...
## [1.2.2](https://github.com/theskumar/python-dotenv/compare/v1.2.1...v1.2.2) - 2026-03-01


### Added


• Support for Python 3.14, including the free-threaded (3.14t) build. (#588)


### Changed


• The `dotenv run` command now forwards flags directly to the specified command by [@bbc2](https://github.com/bbc2) in [#607](https://github.com/theskumar/python-dotenv/issues/607)
• Improved documentation clarity regarding override behavior and the reference
page.
• Updated PyPy support to version 3.11.
• Documentation for FIFO file support.
• Dropped Support for Python 3.9.


...
...
# Changelog
...
## [1.2.2](https://github.com/theskumar/python-dotenv/compare/v1.2.1...v1.2.2) - 2026-03-01
...
### Fixed


• Improved `set_key` and `unset_key` behavior when interacting with symlinks by [@bbc2](https://github.com/bbc2) in [790c5c0](https://github.com/theskumar/python-dotenv/commit/790c5c02991100aa1bf41ee5330aca75edc51311)
• Corrected the license specifier and added missing Python 3.14 classifiers in
package metadata by [@JYOuyang](https://github.com/JYOuyang) in [#590](https://github.com/theskumar/python-dotenv/issues/590)


...
...
# Changelog
...
## [1.2.2](https://github.com/theskumar/python-dotenv/compare/v1.2.1...v1.2.2) - 2026-03-01


### Added
...
### Breaking Changes


• 
`dotenv.set_key` and `dotenv.unset_key` used to follow symlinks in some situations. This is no longer the case. For
that behavior to be restored in all cases, `follow_symlinks=True` should be used.
• 
In the CLI, `set` and `unset` used to follow symlinks in some situations. This is no longer the case.
• 
`dotenv.set_key`, `dotenv.unset_key` and the CLI commands `set` and `unset` used to reset the file mode of the modified .env file to `0o600` in some situations. This is no longer the case: The original mode of the file
is now preserved. Is the file needed to be created or wasn't a regular file, mode
`0o600` is used.


...
...
# Changelog
...
## [1.2.1](https://github.com/theskumar/python-dotenv/compare/v1.2.0...v1.2.1) - 2025-10-26


• Move more config to `pyproject.toml`, removed `setup.cfg`
• Add support for reading `.env` from FIFOs (Unix) by [@sidharth-sudhir](https://github.com/sidharth-sudhir) in [#586](https://github.com/theskumar/python-dotenv/issues/586)


...
...
# Changelog
...
## [1.2.0](https://github.com/theskumar/python-dotenv/compare/v1.1.1...v1.2.0) - 2025-10-26


• Upgrade build system to use PEP 517 & PEP 518 to use `build` and `pyproject.toml` by [@EpicWink](https://github.com/EpicWink) in [#583](https://github.com/theskumar/python-dotenv/issues/583)
• Add support for Python 3.14 by [@23f3001135](https://github.com/23f3001135) in [#579](https://github.com/theskumar/python-dotenv/pull/579)
• Add support for disabling of `load_dotenv()` using `PYTHON_DOTENV_DISABLED` env var. by [@matthewfranglen](https://github.com/matthewfranglen) in [#569](https://github.com/theskumar/python-dotenv/issues/569)


...
...
# Changelog
...
## [1.1.1](https://github.com/theskumar/python-dotenv/compare/v1.1.0...v1.1.1) - 2025-06-24


### Fixed


• CLI: Ensure `find_dotenv` work reliably on python 3.13 by [@theskumar](https://github.com/theskumar) in [#563](https://github.com/theskumar/python-dotenv/pull/563)
• CLI: revert the use of execvpe on Windows by [@wrongontheinternet](https://github.com/wrongontheinternet) in [#566](https://github.com/theskumar/python-dotenv/pull/566)


...
...
# Changelog
...
## [1.1.0](https://github.com/theskumar/python-dotenv/compare/v1.0.1...v1.1.0) - 2025-03-25


### Added


• Add support for python 3.13
• Enhance `dotenv run`, switch to `execvpe` for better resource management and signal handling ([#523](https://github.com/theskumar/python-dotenv/issues/523)) by [@eekstunt](https://github.com/eekstunt)


### Fixed


• `find_dotenv` and `load_dotenv` now correctly looks up at the current directory when running in debugger or pdb
([#553](https://github.com/theskumar/python-dotenv/issues/553) by [@randomseed42](https://github.com/randomseed42))


### Misc


• Drop support for Python 3.8


...
...
# Changelog
...
## [1.0.1](https://github.com/theskumar/python-dotenv/compare/v1.0.0...v1.0.1) - 2024-01-23


### Fixed


• Gracefully handle code which has been imported from a zipfile ([#456](https://github.com/theskumar/python-dotenv/issues/456) by [@samwyma](https://github.com/samwyma))
• Allow modules using `load_dotenv` to be reloaded when launched in a separate thread ([#497](https://github.com/theskumar/python-dotenv/pull/497) by [@freddyaboulton](https://github.com/freddyaboulton))
• Fix file not closed after deletion, handle error in the rewrite function ([#469](https://github.com/theskumar/python-dotenv/issues/469) by [@Qwerty-133](https://github.com/Qwerty-133))


...
...
# Changelog
...
## [1.0.1](https://github.com/theskumar/python-dotenv/compare/v1.0.0...v1.0.1) - 2024-01-23
...
### Misc


• Use pathlib.Path in tests ([#466](https://github.com/theskumar/python-dotenv/issues/466) by [@eumiro](https://github.com/eumiro))
• Fix year in release date in changelog.md ([#454](https://github.com/theskumar/python-dotenv/issues/454) by [@jankislinger](https://github.com/jankislinger))
• Use https in README links ([#474](https://github.com/theskumar/python-dotenv/issues/474) by [@Nicals](https://github.com/Nicals))


...
...
# Changelog
...
## [1.0.0](https://github.com/theskumar/python-dotenv/compare/v0.21.0...v1.0.0) - 2023-02-24


### Fixed


• Drop support for python 3.7, add python 3.12-dev (#449 by [@theskumar](https://github.com/theskumar))
• Handle situations where the cwd does not exist. (#446 by [@jctanner](https://github.com/jctanner))


...
...
# Changelog
...
## [0.21.1](https://github.com/theskumar/python-dotenv/compare/v0.21.0...v0.21.1) - 2023-01-21


### Added


• Use Python 3.11 non-beta in CI (#438 by [@bbc2](https://github.com/bbc2))
• Modernize variables code (#434 by [@Nougat-Waffle](https://github.com/Nougat-Waffle))
• Modernize main.py and parser.py code (#435 by [@Nougat-Waffle](https://github.com/Nougat-Waffle))
• Improve conciseness of cli.py and init.py (#439 by [@Nougat-Waffle](https://github.com/Nougat-Waffle))
• Improve error message for `get` and `list` commands when env file can't be opened (#441 by [@bbc2](https://github.com/bbc2))
• Updated License to align with BSD OSI template (#433 by [@lsmith77](https://github.com/lsmith77))


...
...
# Changelog
...
## [0.21.1](https://github.com/theskumar/python-dotenv/compare/v0.21.0...v0.21.1) - 2023-01-21
...
### Fixed


• Fix Out-of-scope error when "dest" variable is undefined (#413 by [@theGOTOguy](https://github.com/theGOTOguy))
• Fix IPython test warning about deprecated `magic` (#440 by [@bbc2](https://github.com/bbc2))
• Fix type hint for dotenv_path var, add StrPath alias (#432 by [@eaf](https://github.com/eaf))


...
...
# Changelog
...
## [0.21.1](https://github.com/theskumar/python-dotenv/compare/v0.21.0...v0.21.1) - 2023-01-21


### Added
...
### Fixed
...
...
# Changelog
...
## [0.21.0](https://github.com/theskumar/python-dotenv/compare/v0.20.0...v0.21.0) - 2022-09-03


### Added


• CLI: add support for invocations via 'python -m'. (#395 by [@theskumar](https://github.com/theskumar))
• `load_dotenv` function now returns `False`. (#388 by [@larsks](https://github.com/larsks))
• CLI: add --format= option to list command. (#407 by [@sammck](https://github.com/sammck))


...
...
# Changelog
...
## [0.21.0](https://github.com/theskumar/python-dotenv/compare/v0.20.0...v0.21.0) - 2022-09-03
...
### Fixed


• Drop Python 3.5 and 3.6 and upgrade GA (#393 by [@eggplants](https://github.com/eggplants))
• Use `open` instead of `io.open`. (#389 by [@rabinadk1](https://github.com/rabinadk1))
• Improve documentation for variables without a value (#390 by [@bbc2](https://github.com/bbc2))
• Add `parse_it` to Related Projects (#410 by [@naorlivne](https://github.com/naorlivne))
• Update README.md (#415 by [@harveer07](https://github.com/harveer07))
• Improve documentation with direct use of MkDocs (#398 by [@bbc2](https://github.com/bbc2))


...
...
# Changelog
...
## [0.21.0](https://github.com/theskumar/python-dotenv/compare/v0.20.0...v0.21.0) - 2022-09-03


### Added
...
### Fixed
...
...
# Changelog
...
## [0.20.0](https://github.com/theskumar/python-dotenv/compare/v0.19.2...v0.20.0) - 2022-03-24


### Added


• Add `encoding` (`Optional[str]`) parameter to `get_key`, `set_key` and `unset_key`. (#379 by [@bbc2](https://github.com/bbc2))


### Fixed


• Use dict to specify the `entry_points` parameter of `setuptools.setup` (#376 by [@mgorny](https://github.com/mgorny)).
• Don't build universal wheels (#387 by [@bbc2](https://github.com/bbc2)).


## [0.19.2](https://github.com/theskumar/python-dotenv/compare/v0.19.1...v0.19.2) - 2021-11-11


### Fixed


• In `set_key`, add missing newline character before new entry if necessary. (#361 by [@bbc2](https://github.com/bbc2))


...
...
# Changelog
...
## [0.19.1](https://github.com/theskumar/python-dotenv/compare/v0.19.0...v0.19.1) - 2021-08-09


### Added


• Add support for Python 3.10. (#359 by [@theskumar](https://github.com/theskumar))


...
...
# Changelog
...
## [0.19.0](https://github.com/theskumar/python-dotenv/compare/v0.18.0...v0.19.0) - 2021-07-24


### Changed


• Require Python 3.5 or a later version. Python 2 and 3.4 are no longer supported.
(#341 by [@bbc2](https://github.com/bbc2)).


### Added


• The `dotenv_path` argument of `set_key` and `unset_key` now has a type of `Union[str, os.PathLike]` instead of just `os.PathLike` (#347 by [@bbc2](https://github.com/bbc2)).
• The `stream` argument of `load_dotenv` and `dotenv_values` can now be a text stream (`IO[str]`), which includes values like `io.StringIO("foo")` and `open("file.env", "r")` (#348 by [@bbc2](https://github.com/bbc2)).


...
...
# Changelog
...
## [0.18.0](https://github.com/theskumar/python-dotenv/compare/v0.17.1...v0.18.0) - 2021-06-20


### Changed


• Raise `ValueError` if `quote_mode` isn't one of `always`, `auto` or `never` in `set_key` (#330 by [@bbc2](https://github.com/bbc2)).
• When writing a value to a .env file with `set_key` or `dotenv set <key> <value>` (#330 by [@bbc2](https://github.com/bbc2)):
  • Use single quotes instead of double quotes.
  • Don't strip surrounding quotes.
  • In `auto` mode, don't add quotes if the value is only made of alphanumeric characters (as
determined by `string.isalnum`).


...
...
# Changelog
...
## [0.17.1](https://github.com/theskumar/python-dotenv/compare/v0.17.0...v0.17.1) - 2021-04-29


### Fixed


• Fixed tests for build environments relying on `PYTHONPATH` (#318 by [@befeleme](https://github.com/befeleme)).


## [0.17.0](https://github.com/theskumar/python-dotenv/compare/v0.16.0...v0.17.0) - 2021-04-02


### Changed


• Make `dotenv get <key>` only show the value, not `key=value` (#313 by [@bbc2](https://github.com/bbc2)).


### Added


• Add `--override`/`--no-override` option to `dotenv run` (#312 by [@zueve](https://github.com/zueve) and [@bbc2](https://github.com/bbc2)).


...
...
# Changelog
...
## [0.16.0](https://github.com/theskumar/python-dotenv/compare/v0.15.0...v0.16.0) - 2021-03-27


### Changed


• The default value of the `encoding` parameter for `load_dotenv` and `dotenv_values` is now `"utf-8"` instead of `None` (#306 by [@bbc2](https://github.com/bbc2)).
• Fix resolution order in variable expansion with `override=False` (#287 by [@bbc2](https://github.com/bbc2)).


...
...
# Changelog
...
## [0.15.0](https://github.com/theskumar/python-dotenv/compare/v0.14.0...v0.15.0) - 2020-10-28


### Added


• Add `--export` option to `set` to make it prepend the binding with `export` (#270 by [@jadutter](https://github.com/jadutter)).


### Changed


• Make `set` command create the `.env` file in the current directory if no `.env` file was found (#270 by [@jadutter](https://github.com/jadutter)).


...
...
# Changelog
...
## [0.15.0](https://github.com/theskumar/python-dotenv/compare/v0.14.0...v0.15.0) - 2020-10-28
...
### Fixed


• Fix potentially empty expanded value for duplicate key (#260 by [@bbc2](https://github.com/bbc2)).
• Fix import error on Python 3.5.0 and 3.5.1 (#267 by [@gongqingkui](https://github.com/gongqingkui)).
• Fix parsing of unquoted values containing several adjacent space or tab
characters (#277 by [@bbc2](https://github.com/bbc2), review by [@x-yuri](https://github.com/x-yuri)).


...
...
# Changelog
...
## [0.15.0](https://github.com/theskumar/python-dotenv/compare/v0.14.0...v0.15.0) - 2020-10-28


### Added
...
### Changed
...
### Fixed
...
...
# Changelog
...
## [0.14.0](https://github.com/theskumar/python-dotenv/compare/v0.13.0...v0.14.0) - 2020-07-03


### Changed


• Privilege definition in file over the environment in variable expansion (#256 by
[@elbehery95](https://github.com/elbehery95)).


### Fixed


• Improve error message for when file isn't found (#245 by [@snobu](https://github.com/snobu)).
• Use HTTPS URL in package meta data (#251 by [@ekohl](https://github.com/ekohl)).


## [0.13.0](https://github.com/theskumar/python-dotenv/compare/v0.12.0...v0.13.0) - 2020-04-16


### Added


• Add support for a Bash-like default value in variable expansion (#248 by [@bbc2](https://github.com/bbc2)).


...
...
# Changelog
...
## [0.12.0](https://github.com/theskumar/python-dotenv/compare/v0.11.0...v0.12.0) - 2020-02-28


### Changed


• Use current working directory to find `.env` when bundled by PyInstaller (#213 by [@gergelyk](https://github.com/gergelyk)).


### Fixed


• Fix escaping of quoted values written by `set_key` (#236 by [@bbc2](https://github.com/bbc2)).
• Fix `dotenv run` crashing on environment variables without values (#237 by [@yannham](https://github.com/yannham)).
• Remove warning when last line is empty (#238 by [@bbc2](https://github.com/bbc2)).


...
...
# Changelog
...
## [0.11.0](https://github.com/theskumar/python-dotenv/compare/v0.10.5...v0.11.0) - 2020-02-07


### Added


• Add `interpolate` argument to `load_dotenv` and `dotenv_values` to disable interpolation (#232 by [@ulyssessouza](https://github.com/ulyssessouza)).


### Changed


• Use logging instead of warnings (#231 by [@bbc2](https://github.com/bbc2)).


### Fixed


• Fix installation in non-UTF-8 environments (#225 by [@altendky](https://github.com/altendky)).
• Fix PyPI classifiers (#228 by [@bbc2](https://github.com/bbc2)).


...
...
# Changelog
...
## [0.10.5](https://github.com/theskumar/python-dotenv/compare/v0.10.4...v0.10.5) - 2020-01-19


### Fixed


• Fix handling of malformed lines and lines without a value (#222 by [@bbc2](https://github.com/bbc2)):
  • Don't print warning when key has no value.
  • Reject more malformed lines (e.g. "A: B", "a='b',c").
• Fix handling of lines with just a comment (#224 by [@bbc2](https://github.com/bbc2)).


...
...
# Changelog
...
## [0.10.4](https://github.com/theskumar/python-dotenv/compare/v0.10.3...v0.10.4) - 2020-01-17


### Added


• Make typing optional (#179 by [@techalchemy](https://github.com/techalchemy)).
• Print a warning on malformed line (#211 by [@bbc2](https://github.com/bbc2)).
• Support keys without a value (#220 by [@ulyssessouza](https://github.com/ulyssessouza)).


...
...
# Changelog
...
## 0.10.3


• Improve interactive mode detection ([@andrewsmith](https://github.com/andrewsmith))([#183](https://github.com/theskumar/python-dotenv/issues/183)).
• Refactor parser to fix parsing inconsistencies ([@bbc2](https://github.com/bbc2))([#170](https://github.com/theskumar/python-dotenv/issues/170)).
  • Interpret escapes as control characters only in double-quoted strings.
  • Interpret `#` as start of comment only if preceded by whitespace.


...
...
# Changelog
...
## 0.10.2


• Add type hints and expose them to users ([@qnighy](https://github.com/qnighy))([#172](https://github.com/theskumar/python-dotenv/issues/172))
• `load_dotenv` and `dotenv_values` now accept an `encoding` parameter, defaults to `None` ([@theskumar](https://github.com/theskumar))([@earlbread](https://github.com/earlbread))([#161](https://github.com/theskumar/python-dotenv/issues/161))
• Fix `str`/`unicode` inconsistency in Python 2: values are always `str` now. ([@bbc2](https://github.com/bbc2))([#121](https://github.com/theskumar/python-dotenv/issues/121))
• Fix Unicode error in Python 2, introduced in 0.10.0. ([@bbc2](https://github.com/bbc2))([#176](https://github.com/theskumar/python-dotenv/issues/176))


...
...
# Changelog
...
## 0.10.1


• Fix parsing of variable without a value ([@asyncee](https://github.com/asyncee))([@bbc2](https://github.com/bbc2))([#158](https://github.com/theskumar/python-dotenv/issues/158))


...
...
# Changelog
...
## 0.10.0


• Add support for UTF-8 in unquoted values ([@bbc2](https://github.com/bbc2))([#148](https://github.com/theskumar/python-dotenv/issues/148))
• Add support for trailing comments ([@bbc2](https://github.com/bbc2))([#148](https://github.com/theskumar/python-dotenv/issues/148))
• Add backslashes support in values ([@bbc2](https://github.com/bbc2))([#148](https://github.com/theskumar/python-dotenv/issues/148))
• Add support for newlines in values ([@bbc2](https://github.com/bbc2))([#148](https://github.com/theskumar/python-dotenv/issues/148))
• Force environment variables to str with Python2 on Windows ([@greyli](https://github.com/greyli))
• Drop Python 3.3 support ([@greyli](https://github.com/greyli))
...
...
# Changelog
...
## 0.10.0
...
• Fix stderr/-out/-in redirection ([@venthur](https://github.com/venthur))
...
...
# Changelog
...
## 0.9.0


• Add `--version` parameter to cli ([@venthur](https://github.com/venthur))
• Enable loading from current directory ([@cjauvin](https://github.com/cjauvin))
• Add 'dotenv run' command for calling arbitrary shell script with .env ([@venthur](https://github.com/venthur))


## 0.8.1


• Add tests for docs ([@Flimm](https://github.com/Flimm))
• Make 'cli' support optional. Use `pip install python-dotenv[cli]`. ([@theskumar](https://github.com/theskumar))


...
...
# Changelog
...
## 0.8.0


• `set_key` and `unset_key` only modified the affected file instead of parsing and re-writing file, this
causes comments and other file entact as it is.
• Add support for `export` prefix in the line.
• Internal refractoring ([@theskumar](https://github.com/theskumar))
• Allow `load_dotenv` and `dotenv_values` to work with `StringIO())` ([@alanjds](https://github.com/alanjds))([@theskumar](https://github.com/theskumar))([#78](https://github.com/theskumar/python-dotenv/issues/78))


## 0.7.1


• Remove hard dependency on iPython ([@theskumar](https://github.com/theskumar))


...
...
# Changelog
...
## 0.7.0


• Add support to override system environment variable via .env. ([@milonimrod](https://github.com/milonimrod)) ([#63](https://github.com/theskumar/python-dotenv/issues/63))
• Disable ".env not found" warning by default ([@maxkoryukov](https://github.com/maxkoryukov)) ([#57](https://github.com/theskumar/python-dotenv/issues/57))


## 0.6.5


• Add support for special characters `\`. ([@pjona](https://github.com/pjona)) ([#60](https://github.com/theskumar/python-dotenv/issues/60))


## 0.6.4


• Fix issue with single quotes ([@Flimm](https://github.com/Flimm)) ([#52](https://github.com/theskumar/python-dotenv/issues/52))


## 0.6.3


• Handle unicode exception in setup.py ([#46](https://github.com/theskumar/python-dotenv/issues/46))


...
...
# Changelog
...
## 0.6.2


• Fix dotenv list command ([@ticosax](https://github.com/ticosax))
• Add iPython Support ([@tillahoffmann](https://github.com/tillahoffmann))


## 0.6.0


• Drop support for Python 2.6
• Handle escaped characters and newlines in quoted values. (Thanks [@iameugenejo](https://github.com/iameugenejo))
• Remove any spaces around unquoted key/value. (Thanks [@paulochf](https://github.com/paulochf))
• Added POSIX variable expansion. (Thanks [@hugochinchilla](https://github.com/hugochinchilla))


## 0.5.1


• Fix `find_dotenv` - it now start search from the file where this function is called from.


## 0.5.0


• Add `find_dotenv` method that will try to find a `.env` file. (Thanks [@isms](https://github.com/isms))


...
...
# Changelog
...
## 0.4.0


• cli: Added `-q/--quote` option to control the behaviour of quotes around values in `.env`. (Thanks [@hugochinchilla](https://github.com/hugochinchilla)).
• Improved test coverage.


## Project links

Data verified by PyPI on Aug 16, 2026 ›
[Source](https://github.com/theskumar/python-dotenv)


## Key dates

PyPI data ›
Released: Aug 17, 2026

 LATEST RELEASE
## 2 maintainers

PyPI data ›[bbc](https://pypi.org/user/bbc/)[theskumar](https://pypi.org/user/theskumar/)
## Credits


Author: [Saurabh Kumar](mailto:me+github@saurabh-kumar.com)


## GitHub Statistics

Data verified by PyPI on Aug 16, 2026 ›
## License


BSD-3-Clause


## Requires


Python >=3.10


## Provides Extra


`cli`


...
...
# Changelog
...
## Tags


`environment variables``deployments``settings``env``dotenv``configurations``python`


...
...
# Changelog
...
## Classifiers


Development Status
  ◦ [5 - Production/Stable](https://pypi.org/search/?c=Development+Status+%3A%3A+5+-+Production%2FStable)
Environment
  ◦ [Web Environment](https://pypi.org/search/?c=Environment+%3A%3A+Web+Environment)
Intended Audience
  ◦ [Developers](https://pypi.org/search/?c=Intended+Audience+%3A%3A+Developers)
  ◦ [System Administrators](https://pypi.org/search/?c=Intended+Audience+%3A%3A+System+Administrators)
Operating System
  ◦ [OS Independent](https://pypi.org/search/?c=Operating+System+%3A%3A+OS+Independent)
Programming Language
  ◦ [Python](https://pypi.org/search/?c=Programming+Language+%3A%3A+Python)
...
...
# Changelog
...
## Classifiers
...
  ◦ [Python :: 3](https://pypi.org/search/?c=Programming+Language+%3A%3A+Python+%3A%3A+3)
  ◦ [Python :: 3.10](https://pypi.org/search/?c=Programming+Language+%3A%3A+Python+%3A%3A+3.10)
  ◦ [Python :: 3.11](https://pypi.org/search/?c=Programming+Language+%3A%3A+Python+%3A%3A+3.11)
  ◦ [Python :: 3.12](https://pypi.org/search/?c=Programming+Language+%3A%3A+Python+%3A%3A+3.12)
  ◦ [Python :: 3.13](https://pypi.org/search/?c=Programming+Language+%3A%3A+Python+%3A%3A+3.13)
...
...
# Changelog
...
## Classifiers
...
  ◦ [Python :: 3.14](https://pypi.org/search/?c=Programming+Language+%3A%3A+Python+%3A%3A+3.14)
  ◦ [Python :: Implementation :: PyPy](https://pypi.org/search/?c=Programming+Language+%3A%3A+Python+%3A%3A+Implementation+%3A%3A+PyPy)
Topic
  ◦ [System :: Systems Administration](https://pypi.org/search/?c=Topic+%3A%3A+System+%3A%3A+Systems+Administration)
  ◦ [Utilities](https://pypi.org/search/?c=Topic+%3A%3A+Utilities)

 Report project as malware 
...
...
# Changelog
...
## Help


## About PyPI


## Contributing to PyPI


...
...
# Changelog
...
## Using PyPI


Status:[ All Systems Operational](https://status.python.org/)


Developed and maintained by the Python community, for the Python community.[Donate today!](https://donate.pypi.org/)


"PyPI", "Python Package Index", and the blocks logos are registered [trademarks](https://pypi.org/trademarks/) of the [Python Software Foundation](https://www.python.org/psf-landing).


© 2026 [Python Software Foundation](https://www.python.org/psf-landing/)[Site map](https://pypi.org/sitemap/)


Deployed from [6dda362](https://github.com/pypi/warehouse/commit/6dda362f94296a0b2113746f8a6743f5c44c25cc)

 Switch to desktop version 
English
español
français
日本語
português (Brasil)
українська
...
...
# Changelog
...
## Using PyPI
...
Ελληνικά
Deutsch
中文 (简体)
中文 (繁體)
русский
עברית
Esperanto
한국어

[AWS Cloud computing and Security Sponsor](https://aws.amazon.com/)[Datadog Monitoring](https://www.datadoghq.com/)[Depot Continuous Integration](https://depot.dev/)[Fastly CDN](https://www.fastly.com/)[Google Download Analytics](https://careers.google.com/)[Sentry Error logging](https://sentry.io/for/python/?utm_source=pypi&utm_medium=paid-community&utm_campaign=python-na-evergreen&utm_content=static-ad-pypi-sponsor-learnmore)[StatusPage Status page](https://statuspage.io/)
...
...
# Changelog
...
## Additional Links
- [Installing packages](https://packaging.python.org/tutorials/installing-packages/) - External link
- [Uploading packages](https://packaging.python.org/tutorials/packaging-projects/) - External link
- [User guide](https://packaging.python.org/) - External link
- [Project name retention](https://www.python.org/dev/peps/pep-0541/) - External link
- [FAQs](https://pypi.org/help/)
- [PyPI Blog](https://blog.pypi.org/) - External link
- [Infrastructure dashboard](https://dtdg.co/pypi) - External link
- [Statistics](https://pypi.org/stats/)
- [Logos & trademarks](https://pypi.org/trademarks/)
- [Our sponsors](https://pypi.org/sponsors/)
- [Bugs and feedback](https://pypi.org/help/#feedback)
...
...
# Changelog
...
## Additional Links
...
- [Contribute on GitHub](https://github.com/pypi/warehouse) - External link
- [Translate PyPI](https://hosted.weblate.org/projects/pypa/warehouse/) - External link
- [Sponsor PyPI](https://pypi.org/sponsors/)
- [Development credits](https://github.com/pypi/warehouse/graphs/contributors) - External link
- [Terms of Service](https://policies.python.org/pypi.org/Terms-of-Service/) - External link
- [Report security issue](https://pypi.org/security/)
- [Code of conduct](https://policies.python.org/python.org/code-of-conduct/) - External link
- [Privacy Notice](https://policies.python.org/pypi.org/Privacy-Notice/) - External link
- [Acceptable Use Policy](https://policies.python.org/pypi.org/Acceptable-Use-Policy/) - External link
...
# Changelog


All notable changes to this project will be documented in this file.


The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased](https://github.com/theskumar/python-dotenv/compare/v1.2.3...HEAD)


## [1.2.3](https://github.com/theskumar/python-dotenv/compare/v1.2.2...v1.2.3) - 2026-08-16
...
## [1.2.2](https://github.com/theskumar/python-dotenv/compare/v1.2.1...v1.2.2) - 2026-03-01
...
## [1.2.1](https://github.com/theskumar/python-dotenv/compare/v1.2.0...v1.2.1) - 2025-10-26
...
...
# Changelog
...
## [1.2.0](https://github.com/theskumar/python-dotenv/compare/v1.1.1...v1.2.0) - 2025-10-26
...
## [1.1.1](https://github.com/theskumar/python-dotenv/compare/v1.1.0...v1.1.1) - 2025-06-24
...
## [1.1.0](https://github.com/theskumar/python-dotenv/compare/v1.0.1...v1.1.0) - 2025-03-25
...
## [1.0.1](https://github.com/theskumar/python-dotenv/compare/v1.0.0...v1.0.1) - 2024-01-23
...
## [1.0.0](https://github.com/theskumar/python-dotenv/compare/v0.21.0...v1.0.0) - 2023-02-24
...
...
# Changelog
...
## [0.21.1](https://github.com/theskumar/python-dotenv/compare/v0.21.0...v0.21.1) - 2023-01-21
...
## [0.21.0](https://github.com/theskumar/python-dotenv/compare/v0.20.0...v0.21.0) - 2022-09-03
...
## [0.20.0](https://github.com/theskumar/python-dotenv/compare/v0.19.2...v0.20.0) - 2022-03-24
...
## [0.19.2](https://github.com/theskumar/python-dotenv/compare/v0.19.1...v0.19.2) - 2021-11-11
...
## [0.19.1](https://github.com/theskumar/python-dotenv/compare/v0.19.0...v0.19.1) - 2021-08-09
...
...
# Changelog
...
## [0.19.0](https://github.com/theskumar/python-dotenv/compare/v0.18.0...v0.19.0) - 2021-07-24
...
## [0.18.0](https://github.com/theskumar/python-dotenv/compare/v0.17.1...v0.18.0) - 2021-06-20
...
## [0.17.1](https://github.com/theskumar/python-dotenv/compare/v0.17.0...v0.17.1) - 2021-04-29
...
## [0.17.0](https://github.com/theskumar/python-dotenv/compare/v0.16.0...v0.17.0) - 2021-04-02
...
## [0.16.0](https://github.com/theskumar/python-dotenv/compare/v0.15.0...v0.16.0) - 2021-03-27
...
...
# Changelog
...
## [0.15.0](https://github.com/theskumar/python-dotenv/compare/v0.14.0...v0.15.0) - 2020-10-28
...
## [0.14.0](https://github.com/theskumar/python-dotenv/compare/v0.13.0...v0.14.0) - 2020-07-03
...
## [0.13.0](https://github.com/theskumar/python-dotenv/compare/v0.12.0...v0.13.0) - 2020-04-16
...
## [0.12.0](https://github.com/theskumar/python-dotenv/compare/v0.11.0...v0.12.0) - 2020-02-28
...
## [0.11.0](https://github.com/theskumar/python-dotenv/compare/v0.10.5...v0.11.0) - 2020-02-07
...
...
# Changelog
...
## [0.10.5](https://github.com/theskumar/python-dotenv/compare/v0.10.4...v0.10.5) - 2020-01-19
...
## [0.10.4](https://github.com/theskumar/python-dotenv/compare/v0.10.3...v0.10.4) - 2020-01-17
...
## 0.10.3
...
## 0.10.2
...
## 0.10.1
...
## 0.10.0
...
## 0.9.0
...
## 0.8.1
...
## 0.8.0
...
## 0.7.1
...
## 0.7.0
...
## 0.6.5
...
## 0.6.4
...
## 0.6.3
...
## 0.6.2
...
## 0.6.0
...
## 0.5.1
...
...
# Changelog
...
## 0.5.0
...
## 0.4.0
...
## Project links
...
## Key dates
...
## 2 maintainers
...
## Credits
...
## GitHub Statistics
...
## License
...
## Requires
...
## Provides Extra
...
## Tags
...
## Classifiers
...
## Help


## About PyPI


## Contributing to PyPI


## Using PyPI
...
## Additional Links
...
Skip to main content  [PyPI](https://pypi.org/) Search PyPI Search
# python-dotenv 1.2.3
...
# python-dotenv
...
# Code of your application, which uses environment variables (e.g. from
...
# `os.getenv`) as if they came from the actual environment.
...
 # Development settings
...
# Changelog
...
````

**Conclusion drawn from this step:** Pinned exact versions for the two dependencies needed so far: **`sqlite-vec==0.1.9`** and **`python-dotenv==1.2.3`**.

---

## 4. Creating the files — completing item 1/4

**Rationale:** With the workspace confirmed empty (step 1) and the technical facts confirmed (steps 2–3), the assistant created the minimal package scaffolding the spec requires ("Create empty `__init__.py` files where packages are implied," spec.md §3), together with `src/config.py` (needed immediately after, since `knowledge_store.py` imports `KNOWLEDGE_DB` from it) in one parallel batch of `create_file` calls.

### Tool call 1 of 3 — `create_file`

**Parameters:**
```json
{
  "filePath": "c:\\Users\\Tanj\\Documents\\llmzoomcamp2026\\Project\\code\\src\\__init__.py",
  "content": ""
}
```

**Raw result:**
```
The following files were successfully edited:
c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code\src\__init__.py
```

### Tool call 2 of 3 — `create_file`

**Parameters:**
```json
{
  "filePath": "c:\\Users\\Tanj\\Documents\\llmzoomcamp2026\\Project\\code\\src\\db\\__init__.py",
  "content": ""
}
```

**Raw result:**
```
The following files were successfully edited:
c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code\src\db\__init__.py
```

### Tool call 3 of 3 — `create_file`

**Parameters:**
```json
{
  "filePath": "c:\\Users\\Tanj\\Documents\\llmzoomcamp2026\\Project\\code\\src\\config.py",
  "content": "<see full content below>"
}
```

**Full content written:**
```python
"""
Central configuration for the MOSFET Selection RAG application.

Loads secrets from `.env` (via python-dotenv) and exposes the
filesystem paths shared by every layer of the application (ingestion,
knowledge storage, retrieval, evaluation, monitoring).

Additional configuration (model identifiers, retrieval parameters, LLM
pricing, the active retrieval approach, etc.) is added here
incrementally as those layers are implemented.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# Loaded as early as possible so every module reading os.environ (LLM
# clients, etc.) sees values from ./.env.
load_dotenv()

# ---------------------------------------------------------------------------
# Base paths
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = BASE_DIR / "data"
RAW_DIR: Path = DATA_DIR / "raw"
MODELS_DIR: Path = BASE_DIR / "models"
EMBEDDING_MODEL_DIR: Path = MODELS_DIR / "embedding"
RERANKER_MODEL_DIR: Path = MODELS_DIR / "reranker"

# ---------------------------------------------------------------------------
# SQLite database files
# ---------------------------------------------------------------------------
KNOWLEDGE_DB: Path = DATA_DIR / "knowledge.db"
MONITORING_DB: Path = DATA_DIR / "monitoring.db"

# ---------------------------------------------------------------------------
# Evaluation artifacts
# ---------------------------------------------------------------------------
GROUND_TRUTH_CSV: Path = DATA_DIR / "ground_truth.csv"
RETRIEVAL_EVAL_RESULTS_JSON: Path = DATA_DIR / "retrieval_eval_results.json"
RETRIEVAL_EVAL_RESULTS_CSV: Path = DATA_DIR / "retrieval_eval_results.csv"
```

**Raw result:**
```
The following files were successfully edited:
c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code\src\config.py
```

---

## ✅ Checkpoint reached: "Completed: Create empty `__init__.py` files for `src` and `src/db` (1/4)"

At this point, both `src/__init__.py` and `src/db/__init__.py` existed as empty package markers, and `src/config.py` had been created alongside them in the same batch (needed by the next step). This is the end of the requested excerpt.

The work continued immediately afterward with item **2/4** (finalizing `src/config.py`, already done above) and **3/4** (writing `src/db/knowledge_store.py` itself), which are outside the scope of this document — see [CONVERSATION_TRANSCRIPT.md](CONVERSATION_TRANSCRIPT.md) for the complete record of the rest of the session.

---

*End of excerpt.*

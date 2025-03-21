# Introduction to future work
A deep comparison of 8 VLMs (some are not VLMs by nature but could be made into one) fine tuned for image dataset. VLMs tested include the following:
```python
    # BLIP
    {
        "processor_name": "Salesforce/blip-image-captioning-base",
        "decoder_class": BlipForConditionalGeneration,
        "decoder_name": "Salesforce/blip-image-captioning-base",
        "requires_original": True
    },

    # GIT-VIT
    {
        "processor_name": "microsoft/git-base",
        "decoder_class": AutoModelForCausalLM,
        "decoder_name": "microsoft/git-base",
        "tokenizer_name": "microsoft/git-base"
    },

    {
        "processor_name": "nlpconnect/vit-gpt2-image-captioning",
        "decoder_class": VisionEncoderDecoderModel,
        "decoder_name": "nlpconnect/vit-gpt2-image-captioning",
        "processor_class": ViTImageProcessor
    },

    {
        "processor_name": "google/vit-base-patch16-224-in21k",
        "decoder_class": BertModel,
        "decoder_name": "google-bert/bert-base-uncased",
        "tokenizer_name":"google-bert/bert-base-uncased"
    },

    #LLAMA 
    {
        "processor_name": "meta-llama/Llama-3.2-11B-Vision",
        "decoder_class": MllamaForConditionalGeneration,
        "decoder_name": "meta-llama/Llama-3.2-11B-Vision"
    },

    # Swin-BERT
    {
        "processor_name": "microsoft/swin-base-patch4-window12-384",
        "decoder_class": BertModel,
        "decoder_name": "google-bert/bert-base-uncased",
        "tokenizer_name": "google-bert/bert-base-uncased"
    },

    # Qwen-VL
    {
        "processor_name": "Ertugrul/Qwen2-VL-7B-Captioner-Relaxed",
        "decoder_class": Qwen2VLForConditionalGeneration,
        "decoder_name": "Qwen/Qwen2-VL-7B-Instruct"
    },

    # DeepSeek Janus
    {
        "processor_name": "deepseek-ai/Janus-Pro-7B",
        "decoder_class": AutoModelForCausalLM,
        "decoder_name": "deepseek-ai/Janus-Pro-7B",
        "processor_class": VLChatProcessor,
        "decoder_kwargs": {"trust_remote_code": True}
    }
```

## HF errors for non natural VLMs
Hugging face's transformers could give errors like `ModelName.forward() got unexpected argument input_ids`. This is beacuse lora passes them down even though we dont send it through our collator. Easy fix is to go to the model's implementation and add `**kwargs`. Example:

Go to `transformers/models/BertModel/modelling_bert.py` and on the forward implementation for the given model's forward() just add `**kwargs` in them.

## Running guide
OPTIONAL: create a conda environment (highly recommended; especially because of how peft and transformers would be modified for our usecase)
```bash
conda create -n captions python=3.10
conda activate captions
```
1. Install necessary libraries
    `pip install -r requirements.txt`
2. Download Dataset
    ```
    # This is for the main training dataset python download.py 
    python download.py --split validation
    ```
3. Clean dataset 
    ```
    python clean_dataset_python.py
    ```
4. Ready to run the code (in inference validation set)
    ```python inference_test.py```

Solve any errors based on peft error guide above.

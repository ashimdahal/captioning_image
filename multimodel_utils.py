from transformers import (
    BlipForConditionalGeneration,
    BartForConditionalGeneration,
    ViTImageProcessor,
    LlamaForCausalLM,
    Pix2StructProcessor,
    Pix2StructForConditionalGeneration,
    Qwen2VLForConditionalGeneration,
    Qwen2VLProcessor,
    Qwen2_5_VLProcessor,
    MllamaProcessor,
    MllamaForConditionalGeneration,
    BlipProcessor,
    Qwen2_5_VLForConditionalGeneration
)
from peft import PeftModel
from PIL import Image
from janus.models import  VLChatProcessor, MultiModalityCausalLM
from transformers.data.data_collator import DataCollatorWithPadding
from janus.utils.io import load_pil_images
from qwen_vl_utils import process_vision_info
import torch


system_message = """You are a Vision Language Model specialized in captioning or providing a short description of them"""

def format_data(sample):
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "image": sample["image_path"],
                },
                {
                    "type": "text",
                    "text": "Give caption to the image",
                },
            ],
        },
    ]
# Custom Data Collator to handle multimodal inputs
class MultimodalCollator(DataCollatorWithPadding):
    def __init__(self, processor, tokenizer ):
        super().__init__(tokenizer)
        self.processor = processor
        
        if isinstance(self.processor, MllamaProcessor):
            self.text_prompt = "<|image|> Give caption to this image like a normal human being. "

    def __call__(self, features):
        # Process text
        text = [item["text"] for item in features]
        text_inputs = self.tokenizer(
            text, 
            padding="max_length", 
            truncation=True, 
            return_tensors="pt",
        )

        # Process images
        images = [item["image"] for item in features]
        if isinstance(self.processor, ViTImageProcessor):
            pixel_values = self.processor(images=images, return_tensors="pt").pixel_values
            return{
                "pixel_values": pixel_values,
                "labels":text_inputs["input_ids"],
                "label_names":text_inputs["input_ids"],
            }

        elif isinstance(self.processor, (
                Qwen2VLProcessor,
                Qwen2_5_VLProcessor,
                MllamaProcessor
            )):
            features = [format_data(feature) for feature in features]
            texts = [
                self.processor.apply_chat_template(
                    example,
                    tokenize=False,
                    add_generation_prompt=True
                ) for example in features
            ]

            processed_outputs = self.processor(
                text=texts,
                images=images,
                return_tensors="pt",
                padding=True
            )
            labels = processed_outputs["input_ids"].clone()
            labels[labels == self.tokenizer.pad_token_id] = -100
            if isinstance(processor, Qwen2VLProcessor):  # Check if the processor is Qwen2VLProcessor
                image_tokens = [151652, 151653, 151655]  # Specific image token IDs for Qwen2VLProcessor
            else:
                image_tokens = [processor.tokenizer.convert_tokens_to_ids(processor.image_token)]  

            labels = processed_outputs["input_ids"].clone()
            for image_token_id in image_tokens:
                labels[labels == image_token_id] = -100

            processed_outputs["labels"] = labels
            return processed_outputs

        elif isinstance(self.processor, VLChatProcessor):
            conversations = [
                {
                    "role": "<|User|>",
                    "content": f"<image_placeholder>\ncaption this image.",
                    "images": [image["image_path"]],
                }
                for image in features
            ]
            processed_outputs = self.processor(
                conversations=conversations,
                images=images, 
                paddint=True,
                return_tensors="pt",
                truncation=True,
                force_batchify=True
            )
        
            labels = processed_outputs["input_ids"].clone()
            labels[labels == self.tokenizer.pad_token_id] = -100
            image_tokens = [self.processor.tokenizer.convert_tokens_to_ids(self.processor.image_token)]
            for image_token_id in image_tokens:
                labels[labels == image_token_id] = -100

            processed_outputs["labels"] = labels
            return {
                "pixel_values":processed_outputs["pixel_values"],
                "labels":labels,
                # "attention_mask":processed_outputs["attention_mask"],
                "images_emb_mask":processed_outputs["images_emb_mask"],
                "images_seq_mask":processed_outputs["images_seq_mask"],
                "input_ids":processed_outputs["input_ids"],
                # "sft_format":processed_outputs["sft_format"]
            }
        elif (isinstance(self.processor, BlipProcessor)):
            processed_outputs = self.processor(
                images=images,
                text=text,
                return_tensors="pt",
                padding="max_length"
            )
            labels = processed_outputs["input_ids"].clone()
            # Mask padding tokens.
            processed_outputs["labels"] = labels

            return processed_outputs
        else:
            processed_outputs = self.processor(
                images=images,
                text=text,
                return_tensors="pt",
                padding="max_length"
            )

        labels = processed_outputs["input_ids"].clone() # Mask padding tokens.
        labels[labels == self.processor.tokenizer.pad_token_id] = -100
        
        return {
            "pixel_values": processed_outputs["pixel_values"],
            "input_ids": processed_outputs["input_ids"],
            "attention_mask": text_inputs["attention_mask"],
            "labels": labels,
            "label_names":labels
        }

# Custom Model Wrapper
class MultimodalModel(torch.nn.Module):
    def __init__(self, processor, decoder, tokenizer, freeze_vision_encoder=False):
        super().__init__()
        self.processor = processor
        self.decoder = decoder
        self.tokenizer = tokenizer
        
        self.has_vision_encoder = hasattr(self.decoder, "vision_model") or hasattr(self.decoder, "encoder")

        self.orig_instance = self.decoder.base_model.model if isinstance(decoder, PeftModel) else self.decoder
        # Freeze vision encoder if required
        if freeze_vision_encoder and self.has_vision_encoder:
            vision_encoder = getattr(self.decoder, "vision_model", None) or getattr(self.decoder, "encoder", None)
            if vision_encoder:
                for param in vision_encoder.parameters():
                    param.requires_grad = False

    def forward(self, **kwargs):
        # Handle different model architectures
        if isinstance(self.orig_instance, (
            BlipForConditionalGeneration,
            LlamaForCausalLM,
            BartForConditionalGeneration,
            Pix2StructForConditionalGeneration,
            Qwen2VLForConditionalGeneration,
            MllamaForConditionalGeneration,
            Qwen2_5_VLForConditionalGeneration
        )):
            # Encoder-decoder models
            outputs = self.decoder(
                **kwargs
            )
        elif isinstance(self.orig_instance, MultiModalityCausalLM):
            # the language model is a wrapper for llammaforcasualLM
            embeddings = self.decoder.prepare_inputs_embeds(**kwargs)
            outputs = self.decoder.language_model(
                inputs_embeds=embeddings,
                attention_mask=kwargs["attention_mask"],
                pad_token_id=self.tokenizer.eos_token_id,
                bos_token_id=self.tokenizer.bos_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                max_new_tokens=40,
                # use_cache=True,
                labels=kwargs["labels"]
            )
        else:
            # fallback 
            inputs_embeds = self.decoder.get_input_embeddings()(kwargs["input_ids"])
            
            # Combine visual and text embeddings
            visual_features = self.decoder.vision_model(kwargs["pixel_values"]).last_hidden_state
            combined_embeds = torch.cat([visual_features, inputs_embeds], dim=1)
            
            outputs = self.decoder(
                **kwargs
            )
            
        return outputs


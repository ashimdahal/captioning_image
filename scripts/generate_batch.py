import os
import json
import torch
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from PIL import Image
from diffusers import StableDiffusion3Pipeline
from transformers import CLIPProcessor, CLIPModel
from tqdm.auto import tqdm
from torch.utils.data import Dataset, DataLoader

class CaptionImageDataset(Dataset):
    """Dataset returning (caption, output_path) pairs."""
    def __init__(self, captions, output_paths):
        assert len(captions) == len(output_paths)
        self.captions = captions
        self.paths = output_paths

    def __len__(self):
        return len(self.captions)

    def __getitem__(self, idx):
        return self.captions[idx], self.paths[idx]

def generate_images_dataloader(pipe, captions, output_paths,
                               num_inference_steps=50, batch_size=16):
    """
    Generates images in batches via a DataLoader.
    - captions:     list of prompt strings
    - output_paths: list of filepaths where images will be saved
    - batch_size:   number of prompts per forward pass
    """
    dataset = CaptionImageDataset(captions, output_paths)
    loader  = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=2)

    for batch in tqdm(loader, desc="Generating images"):
        batch_captions, batch_paths = batch
        # Make sure to cast batch_captions to a list of str
        images = pipe(prompt=list(batch_captions), num_inference_steps=num_inference_steps).images
        for img, path in zip(images, batch_paths):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            img.save(path)
        torch.cuda.empty_cache()

def setup_models():
    """Set up SDXL and CLIP models"""
    # Set up SDXL
    sdxl_pipe =StableDiffusion3Pipeline.from_pretrained(
        "stabilityai/stable-diffusion-3-medium-diffusers",
        torch_dtype=torch.float16
    )
    sdxl_pipe = sdxl_pipe.to("cuda")
    
    # Set up CLIP for similarity
    clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to("cuda")
    clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    
    return sdxl_pipe, clip_model, clip_processor

def calculate_similarity(clip_model, clip_processor, img1_path, img2_path):
    img1 = Image.open(img1_path).convert("RGB")
    img2 = Image.open(img2_path).convert("RGB")
    inputs = clip_processor(images=[img1, img2], return_tensors="pt", padding=True).to("cuda")
    with torch.no_grad():
        feats = clip_model.get_image_features(**inputs)
    f1 = feats[0:1] / feats[0:1].norm(dim=1, keepdim=True)
    f2 = feats[1:2] / feats[1:2].norm(dim=1, keepdim=True)
    return torch.nn.functional.cosine_similarity(f1, f2).item()

def process_models_generate_store(output_dir, samples_json_path,
                                  batch_size=16, num_inference_steps=50,
                                  results_json_path="similarity_scores.json"):
    save_samples = 3000
    os.makedirs(output_dir, exist_ok=True)
    with open(samples_json_path, 'r') as f:
        all_samples = json.load(f)

    pipe, clip_model, clip_processor = setup_models()
    results = []

    first_samples = next(iter(all_samples.values()))

    refs = [s["base_caption"]  for s in first_samples][:save_samples]
    origs = [s["image_path"] for s in first_samples][:save_samples]
    image_ids = [os.path.splitext(os.path.basename(p))[0] for p in origs][:save_samples]


    refs_dir = os.path.join(output_dir, "references")
    if not os.path.isdir(refs_dir):
        os.makedirs(refs_dir, exist_ok=True)
        ref_out = [
            os.path.join(refs_dir, f"{img_id}_ref.png")
            for img_id in image_ids
        ]
        generate_images_dataloader(
            pipe, refs, ref_out,
            num_inference_steps=num_inference_steps,
            batch_size=batch_size
        )
    else:
        print(f"↳ Skipping reference gen; '{refs_dir}' already exists.")

    for model_name, samples in tqdm(all_samples.items(), desc="Models"):
        display_name = model_name

        preds = [s["generated_caption"] for s in samples][:save_samples]
        origs = [s["image_path"] for s in samples][:save_samples]
        image_ids = [os.path.splitext(os.path.basename(p))[0] for p in origs][:save_samples]

        preds_dir = os.path.join(output_dir, "predictions", display_name)
        if os.path.isdir(preds_dir):
            continue
        os.makedirs(preds_dir, exist_ok=True)

        pred_out = [
            os.path.join(preds_dir, f"{display_name}_{img_id}_pred.png")
            for img_id in image_ids
        ]
        generate_images_dataloader(
            pipe, preds, pred_out,
            num_inference_steps=num_inference_steps,
            batch_size=batch_size
        )

    #     # Compute similarities between original and predicted images
    #     for img_id, orig_path, p_out, pred in zip(image_ids, origs, pred_out, preds):
    #         base_img = os.path.join("valid_dataset", os.path.basename(orig_path))
    #
    #         if os.path.exists(base_img):
    #             sim_pred = calculate_similarity(clip_model, clip_processor, base_img, p_out)
    #         else:
    #             sim_pred = 0.0
    #
    #         results.append({
    #             "model":           display_name,
    #             "dataset_index":   int(img_id),
    #             "base_img":        base_img,
    #             "pred_img":        p_out,
    #             "prediction":      pred,
    #             "pred_similarity": sim_pred,
    #         })
    #
    # # Store the results in a JSON file
    # with open(results_json_path, 'w') as outfile:
    #     json.dump(results, outfile, indent=4)
    #
    # print(f"Similarity scores and metadata saved to: {results_json_path}")
    # create_visualization(results, output_dir) # You can uncomment this if you still want visualization
    return results

if __name__ == "__main__":
    results_file = "similarity_scores.json"
    results = process_models_generate_store(
        output_dir="model_comparison_batch_coco",
        samples_json_path="output_coco.json",
        batch_size=16,
        num_inference_steps=40,
        results_json_path=results_file
    )
    print(f"Processed {len(results)} samples.")

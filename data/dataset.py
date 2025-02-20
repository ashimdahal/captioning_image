import numpy as np
import os
import torch
import PIL.Image
import io
import urllib
from torch.utils.data import Dataset

class ConceptualCaptionsDataset(Dataset):
    def __init__(self, dataset, cache_dir="dataset",  transform=None):
        """
        Args:
            dataset: Hugging Face dataset with image URLs and captions.
            cache_dir: Directory to store downloaded images.
            transform: Optional image transformations.
        """
        self.dataset = dataset
        self.cache_dir = cache_dir
        self.transform = transform

        # Create cache directory if it doesn't exist
        os.makedirs(self.cache_dir, exist_ok=True)

    def fetch_image(self, image_url, image_id):
        """Downloads image if not cached, otherwise loads from disk."""
        image_path = os.path.join(self.cache_dir, f"{image_id}.jpg")

        # If image exists, load from disk
        if os.path.exists(image_path):
            return PIL.Image.open(image_path).convert("RGB")

        # Otherwise, download and save it
        try:
            request = urllib.request.Request(image_url, headers={"user-agent": "datasets"})
            with urllib.request.urlopen(request, timeout=5) as req:
                image = PIL.Image.open(io.BytesIO(req.read())).convert("RGB")
                image.save(image_path, "JPEG")  # Save to cache
            return image
        except Exception:
            return None  # Return None for failed downloads

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, idx):
        data = self.dataset[idx]
        image_url = data["image_url"]
        caption = data["caption"]

        # Generate a unique image ID based on index
        image_id = str(idx)

        image = self.fetch_image(image_url, image_id)

        # If the image fails to load, return a blank tensor
        if image is None:
            image = PIL.Image.new("RGB", (400, 400), (255, 255, 255))  # White placeholder

        if self.transform:
            image = np.array(image)
            image = self.transform(image=image)["image"]

        return {
            "image": PIL.Image.fromarray(image),
            "text": caption,
            "image_path":f"{self.cache_dir}/{image_id}.jpg" # for janus pro only
        }


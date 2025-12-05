"""
This file is part of PyCortexMDebug

PyCortexMDebug is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

PyCortexMDebug is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with PyCortexMDebug.  If not, see <http://www.gnu.org/licenses/>.



Fetch SVD files from the cmsis-svd GitHub repository without cloning it.
"""

import requests
from typing import List, Dict, Optional
from pathlib import Path
import json
import os
import dataclasses
import time


def _str_or_env(default: str, env_var: str) -> str:
    env = os.getenv(env_var)
    return default if env is None else env


_REPO_OWNER = "cmsis-svd"
_REPO_NAME = "cmsis-svd-data"
_BRANCH = _str_or_env("main", "SVD_BRANCH")
_BASE_API_URL = _str_or_env(f"https://api.github.com/repos/{_REPO_OWNER}/{_REPO_NAME}", "SVD_API_URL")
_DEFAULT_CACHE_PATH = Path(_str_or_env(str(Path.home() / ".cache" / "cmsis-svd"), "SVD_CACHE_PATH"))

_VERBOSE = True

def _log(s: str):
    if _VERBOSE:
        print(s)

@dataclasses.dataclass
class RemoteSVDFile:
    vendor: str
    name: str
    download_url: str
    size: str

    def as_dict(self) -> Dict[str, str]:
        return {"vendor": self.vendor, "name": self.name, "download_url": self.download_url, "size": self.size}

    @staticmethod
    def from_dict(d: Dict[str, str]) -> "RemoteSVDFile":
        return RemoteSVDFile(d["vendor"], d["name"], d["download_url"], d["size"])


class SVDFetcher:
    """Fetch SVD files from cmsis-svd repository via GitHub API."""

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize the SVD fetcher.

        Args:
            cache_dir: Directory to cache downloaded SVD files.
                      Defaults to ~/.cache/svd-fetcher/
        """
        if cache_dir is None:
            cache_dir = _DEFAULT_CACHE_PATH
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "devices.json"

        self.session = requests.Session()
        # Add GitHub token if available via environment variable
        # This increases rate limits from 60/hr to 5000/hr
        if token := os.environ.get("GITHUB_TOKEN"):
            self.session.headers["Authorization"] = f"token {token}"

    def save(self, vendors: Dict[str, List[RemoteSVDFile]]):
        all_tuples = [(vendor, [c.as_dict() for c in chips]) for vendor, chips in vendors.items()]
        serializable_dict: Dict[str, List[Dict[str, str]]] = {}
        for (vendor, chips) in all_tuples:
            serializable_dict[vendor] = chips

        open(str(self.cache_file), "w").write(json.dumps(serializable_dict))

    def cache_age_seconds(self) -> Optional[int]:
        """Get approximate time since cache file was modified

        Returns:
            Optional[int]: seconds since modification or None if nonexistent
        """
        if not self.cache_file.exists():
            return None
        mtime = os.path.getmtime(str(self.cache_file.absolute()))

        return int(time.time() - mtime)


    def restore(self) -> Optional[Dict[str, List[RemoteSVDFile]]]:
        if self.cache_file.exists():
            _log(f"Restoring cached index from {self.cache_file}")
            raw: Dict[str, List[Dict[str, str]]] = json.loads(open(str(self.cache_file)).read())
            good_dict: Dict[str, List[RemoteSVDFile]] = dict()
            # Raw _should_ be dict of vendors with a list of chips under each
            for (vendor, chips_dicts) in raw.items():
               chips = [RemoteSVDFile.from_dict(chip_dict) for chip_dict in chips_dicts]
               good_dict[vendor] = chips
            return good_dict

        return None







    def get_vendors(self) -> List[str]:
        """
        Get list of available vendors.

        Returns:
            Sorted list of vendor names
        """
        url = f"{_BASE_API_URL}/contents/data"
        params = {"ref": _BRANCH}

        response = self.session.get(url, params=params)
        response.raise_for_status()

        contents = response.json()
        vendors = [item["name"] for item in contents if item["type"] == "dir"]
        return sorted(vendors)

    def get_chips_for_vendor(self, vendor: str) -> List[RemoteSVDFile]:
        """
        Get list of available chips for a specific vendor.

        Args:
            vendor: Vendor name (e.g., "STMicro", "NXP")

        Returns:
            List of dicts with keys: 'name', 'download_url', 'size'
        """
        url = f"{_BASE_API_URL}/contents/data/{vendor}"
        params = {"ref": _BRANCH}

        response = self.session.get(url, params=params)
        response.raise_for_status()

        contents = response.json()
        chips: List[RemoteSVDFile] = []
        for item in contents:
            if item["type"] == "file" and item["name"].endswith(".svd"):
                chips.append(
                    RemoteSVDFile(
                        vendor=vendor,
                        name=item["name"],
                        download_url=item["download_url"],
                        size=item["size"]))
        return sorted(chips, key=lambda x: x.name)

    def get_all_chips(self) -> Dict[str, List[RemoteSVDFile]]:
        """
        Get all vendors and their chips with download URLs.

        Returns:
            Dict mapping vendor name to list of chip info dicts
        """
        vendors = self.get_vendors()
        all_data = {}

        for vendor in vendors:
            chips = self.get_chips_for_vendor(vendor)
            all_data[vendor] = chips

        return all_data

    def download_svd(self, chip: RemoteSVDFile, force: bool = False) -> Path:
        """
        Download an SVD file for a specific chip.

        Args:
            chip: The RemoteSVDFile for the chip
            force: If True, re-download even if cached

        Returns:
            Path to the downloaded SVD file
        """
        # Check cache first
        cached_file = self.cache_dir / chip.vendor / chip.name
        if cached_file.exists() and not force:
            _log(f"Using cached file {chip.vendor}->{chip.name} at {cached_file}")
            return cached_file

        # Download the file
        _log(f"Downloading {chip.vendor}->{chip.name}, url {chip.download_url}, to {cached_file}")
        response = self.session.get(chip.download_url)
        response.raise_for_status()

        # Save to cache
        cached_file.parent.mkdir(parents=True, exist_ok=True)
        cached_file.write_bytes(response.content)

        return cached_file

    def search_chip(self, query: str) -> List[RemoteSVDFile]:
        """
        Search for chips matching a query string.

        Args:
            query: Search string (case-insensitive)

        Returns:
            List of matching chips with vendor, name, and download_url
        """
        query_lower = query.lower()
        matches = []

        all_chips = self.get_all_chips()
        for vendor, chips in all_chips.items():
            for chip in chips:
                if query_lower in chip.name.lower():
                    matches.append(chip)

        return matches


def main():
    """Example usage."""
    fetcher = SVDFetcher()

    # List vendors
    print("Available vendors:")
    vendors = fetcher.get_vendors()
    for vendor in vendors:
        print(f"  {vendor}")

    print(f"\nTotal vendors: {len(vendors)}")

    # Show chips for first vendor as example
    if vendors:
        example_vendor = vendors[0]
        print(f"\nChips for {example_vendor}:")
        chips = fetcher.get_chips_for_vendor(example_vendor)
        for chip in chips[:5]:
            print(f"  {chip.name}")
        print(f"  ... ({len(chips)} total)")

    # Example: search for STM32F4 chips
    print("\nSearching for 'STM32F4' chips:")
    results = fetcher.search_chip("STM32F4")
    for result in results[:10]:
        print(f"  {result.vendor}/{result.name}")

    # Example: download a specific chip
    if results:
        first = results[0]
        print(f"\nDownloading {first.vendor}/{first.name}...")
        path = fetcher.download_svd(first)
        print(f"Saved to: {path}")


if __name__ == "__main__":
    main()

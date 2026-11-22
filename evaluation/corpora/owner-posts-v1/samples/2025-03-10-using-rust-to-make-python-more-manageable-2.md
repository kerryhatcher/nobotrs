---
layout: post
title: "Using Rust to make Python more manageable"
dek: "It has long been best practice to use virtual python environments with locally installed libraries rather than system ones. However, setting up and managing those can be a hassle. Tools like pipx, pyenv and poetry went a long way to making life much easier but they have their own drawbacks. "
date: 2025-03-10T17:14:58.000-04:00
tags:
  - "Python"
  - "Software Development"
  - "News"
  - "#Import 2025-06-30 17:59"
  - "#Import 2025-07-15 14:46"
authors:
  - "Kerry Hatcher"
feature_image: "https://images.unsplash.com/photo-1591643958857-e6623f63c0e5?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3wxMTc3M3wwfDF8c2VhcmNofDl8fHJ1c3R8ZW58MHx8fHwxNzQxNjQwMjMwfDA&ixlib=rb-4.0.3&q=80&w=2000"
feature_image_caption: "<span style=\"white-space: pre-wrap;\">Photo by </span><a href=\"https://unsplash.com/@zmachacek?utm_source=ghost&amp;utm_medium=referral&amp;utm_campaign=api-credit\"><span style=\"white-space: pre-wrap;\">Zdeněk Macháček</span></a><span style=\"white-space: pre-wrap;\"> / </span><a href=\"https://unsplash.com/?utm_source=ghost&amp;utm_medium=referral&amp;utm_campaign=api-credit\"><span style=\"white-space: pre-wrap;\">Unsplash</span></a>"
ghost_id: "6876a213df7b2049e70a063d"
ghost_url: "https://www.kerryhatcher.com/using-rust-to-make-python-more-manageable-2/"
---

---

[![](/assets/images/remote/hatchdata/images/2025/03/logo-letter.svg)](https://docs.astral.sh/uv/?ref=kerryhatcher.com)

## Introducing UV

> "An extremely fast Python package and project manager, written in Rust."

[UV](https://docs.astral.sh/uv/?ref=kerryhatcher.com) is my new favorite Python tool, and it’s not even written in Python. This handy little CLI tool makes setting up a new Python project incredibly simple, thanks to sensible defaults and a streamlined workflow. With UV, you can avoid the typical headaches of environment management and package installation.

### Why UV?

1. **Blazing Fast** – Because UV is written in Rust, it is much faster than traditional Python-based tools.
2. **Minimal Dependencies** – Unlike tools that require their own virtual environments or Python installations, UV operates independently.
3. **Unified Package Management** – UV combines environment creation and package installation in a seamless way.
4. **Drop-in Replacement** – UV aims to be a drop-in replacement for `pip`, `pip-tools`, `virtualenv`, `venv`, `pipx`, and even aspects of `poetry`.

### Getting Started with UV

First, you’ll need to install UV. If you’re on a Unix-based system, you can install it using the following command:

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Windows, you can download and install it manually from the [official UV documentation](https://docs.astral.sh/uv/?ref=kerryhatcher.com).

Once installed, you can create a new Python project and manage its dependencies effortlessly:

```
uv venv my_project
cd my_project
uv pip install requests
```

UV automatically creates a virtual environment and installs packages in it without needing separate activation commands.

### A Better Workflow

UV simplifies Python project workflows in several ways:

* **Automatic virtual environment management** – No need to manually set up or activate environments.
* **Lightning-fast dependency resolution** – UV outperforms `pip` and `poetry` in many cases.
* **Cross-platform support** – Works seamlessly across different operating systems.

### Final Thoughts

Python developers are always on the lookout for tools that reduce friction and improve efficiency. UV stands out as a game-changer in package management and virtual environments. If you’re tired of slow dependency resolution, confusing package installations, or clunky environment setups, UV is definitely worth a try.

You can find more details and documentation at [UV's official website](https://docs.astral.sh/uv/?ref=kerryhatcher.com). Happy coding!

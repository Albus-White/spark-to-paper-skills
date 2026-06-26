<h1 align="center">DrawAI: Make Raster Figures Editable</h1>

<p align="center">
  <a href="https://github.com/Renaissance-Mind/DrawAI-dev"><img alt="Repository" src="https://img.shields.io/badge/repo-DrawAI-111827"></a>
  <a href="https://drawai.renaissancemind.ai/demo"><img alt="Demo" src="https://img.shields.io/badge/demo-online-F59E0B"></a>
  <a href="https://drawai.renaissancemind.ai"><img alt="Website" src="https://img.shields.io/badge/website-DrawAI-0EA5E9"></a>
  <img alt="arXiv" src="https://img.shields.io/badge/arXiv-TODO-DC2626">
  <img alt="Python" src="https://img.shields.io/badge/python-3.12%2B-2563EB">
  <img alt="License" src="https://img.shields.io/badge/license-Apache--2.0-7C3AED">
  <a href="README.md">简体中文</a>
</p>

**DrawAI turns raster paper figures, technical diagrams, and slide screenshots into editable SVG and PPTX artifacts.**

It decomposes input images into structure, text, and local assets, then generates vector results that are easier to keep editing. Use it as a CLI, or start the Workbench in the browser for batch uploads, progress tracking, and artifact management.

<a id="demo"></a>
## 🎬 Demo

https://github.com/user-attachments/assets/59a81ac2-cdbe-49b6-a4fa-8db897afc6bb

<details>
<summary>Changelog</summary>

### 2026-06-18

- Added the Agent CLI backend for asset analysis and SVG generation, with support for `codex cli`, `claude`, `kimi-code`, `OpenClaw`, `Hermes`, and custom agent commands.
- Added Codex SDK image generation and editing support, and exposed those image-generation flows in the Workbench.
- Added native Windows deployment support, including packaged Codex CLI detection, launcher output flushing, platform-safe launcher tests, and README documentation.
- Added Workbench runtime and queue visibility so users can see backend runtime status while tasks are running.
- Hardened inherited Codex provider configuration so local and nested runtime configs resolve more reliably.
- Improved SVG generation resilience by extending Codex recovery timeout behavior and disabling SAM mask output by default in the public path.

### 2026-06-17

- Published the initial DrawAI source snapshot.
- Exposed mask and polygon geometry in asset review so users can inspect richer asset boundaries before SVG/PPTX generation.

</details>

<a id="roadmap"></a>
## 🗺️ Roadmap

For open-source stability, DrawAI currently keeps some still-under-validation capabilities out of the public path. These features will be tested and opened progressively after cross-platform validation, dependency cleanup, and license review.

- [x] Support Windows systems (native deployment is supported; macOS and Linux remain compatible)
- [ ] Support polygon and irregular masks
- [ ] Support asset redrawing with GPT-Image-2
- [ ] Support more complex generation modes, including image-generation skills
- [ ] Support skill-based usage
- [ ] Support other agents and models (already supports `codex cli`, `claude`, `kimi-code`, `OpenClaw`, `Hermes`)

> Note: Because mask and redraw capabilities are currently reduced in the open-source path, robustness on full-image complex backgrounds is lower than the internal target. Support is being added rapidly.

<a id="quick-start"></a>
## ⚡ Quick Start

### Option 1: 🧑‍💻 Workbench

Workbench starts the model services, backend API, and frontend together. It is more convenient for repeated testing, batch uploads, progress inspection, and artifact review.

```bash
uv run drawai setup local
uv run drawai workbench
```

Open the frontend:

```text
http://127.0.0.1:5174/
```

To make the Workbench available on your local network, bind it to all network interfaces:

```bash
uv run drawai workbench --host 0.0.0.0
```

Then visit it with the machine's real LAN IP, for example:

```text
http://192.168.50.10:5174/
```

Remote model services, split Workbench API deployment, ports, and staged config-file runs are documented in [runtime options](docs/zh-CN/runtime-options.md).

### Option 2: 🖥️ CLI

This is the simplest single-machine path and the best way to confirm that DrawAI runs correctly.

```bash
uv run drawai setup local
uv run drawai run examples/demo_figure.png --local
```

`setup local` automatically runs a doctor check after it finishes.

Run your own image:

```bash
uv run drawai run /path/to/your/image.png --local --run-name my_first_drawai_run
```

Use the same device profile during setup and runtime when you want NVIDIA GPU or Apple Silicon MPS support:

```bash
uv run drawai setup local --device gpu
uv run drawai run /path/to/your/image.png --local --device gpu
```

```bash
uv run drawai setup local --device mps
uv run drawai run /path/to/your/image.png --local --device mps
```

## 🧰 Requirements

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)
- Node.js 20.19+ or 22.12+ for the Workbench frontend
- Working Codex/OpenAI authentication, or a configured agent CLI such as Kimi (`kimi`), Claude (`claude`), Codex (`codex exec`), OpenClaw (`openclaw agent`), or Hermes (`hermes chat`), for run0 asset analysis and SVG generation
- >8 GB disk space for model weights and the installed runtime environment

The default local runtime directory is:

```text
.local/drawai_runtime/
```

It is not tracked by git. Model downloads use ModelScope by default. See [runtime options](docs/zh-CN/runtime-options.md) for Hugging Face downloads, manual model paths, Torch backend selection, custom ports, and other advanced settings.

### Choose Codex SDK Or Agent CLI

The default config continues to use the Codex Python SDK. To use a direct CLI instead, switch the SVG backend and runtime provider to `agent_cli`, then choose `kimi`, `claude`, `codex`, `openclaw`, `hermes`, or a custom command under `model_runtime.cli`:

```yaml
svg:
  generation_backend: agent_cli
model_runtime:
  provider: agent-cli
  connection_id: kimi
  cli:
    agent: kimi
    command:
      - kimi
```

The Agent CLI path is used for both run0 asset analysis and SVG generation. No config change is needed when staying on the Codex SDK. For Claude, Codex, OpenClaw, or Hermes CLI, change `agent` and `command` to the corresponding command, for example `claude`, `codex exec`, `openclaw agent`, or `hermes chat`.

<a id="outputs"></a>
## 📦 Output Locations

CLI runs write timestamped folders under:

```text
runs/<date>/<time>_<run-name>/
```

The most useful files are usually:

```text
reports/run_summary.json
outputs/case_001_*/
  reports/pipeline_summary.json
  box_ir/box_ir.json
  svg/semantic.svg
  svg/rendered.png
  svg_to_ppt/semantic.svg_to_ppt.pptx
```

Workbench tasks and uploaded files are stored by default under:

```text
.local/workbench/
```

## 💬 Contact Us

Feel free to open a [GitHub issue](https://github.com/Renaissance-Mind/DrawAI-dev/issues) or submit a PR. You can also scan the QR code to join the DrawAI WeChat group for testing and updates.

<p align="center">
  <img src="wechat.jpg" alt="DrawAI WeChat group QR code" width="260">
</p>

## 🧩 Artifact Types

DrawAI is not meant to simply place the original bitmap into a PowerPoint file. It tries to produce artifacts that are editable, inspectable, and suitable for further work:

- `svg`: the primary editable vector result
- `pptx`: export artifact ready for slide workflows
- `psd`: TODO

The PPTX export path always uses the bundled native-shape converter, mapping SVG primitives, text, and local images to PowerPoint native DrawingML shapes and images. SVG embedding and external converter switching are no longer exposed.

## 📚 Documentation

- [Runtime options, ports, and model paths](docs/zh-CN/runtime-options.md)
- [Changelog](CHANGELOG.md)

## ❓ FAQ

**Q: What should I do if I see `Refresh Codex login or set a working OPENAI_API_KEY before SVG generation.`?**

A: Log in to Codex again before setup:

```bash
codex login
```

## 🙏 Acknowledgements

DrawAI's design and implementation were informed by ideas and practices from these open-source projects:

- [hugohe3/ppt-master](https://github.com/hugohe3/ppt-master)
- [ningzimu/image-to-editable-ppt-skill](https://github.com/ningzimu/image-to-editable-ppt-skill)
- [llmsresearch/paperbanana](https://github.com/llmsresearch/paperbanana)
- [ResearAI/AutoFigure-Edit](https://github.com/ResearAI/AutoFigure-Edit)

## ⚖️ License And Commercial Use

DrawAI source code is released under Apache-2.0. The source-code license permits commercial use, modification, and redistribution.

Third-party models, model weights, fonts, and external services follow their own upstream terms.

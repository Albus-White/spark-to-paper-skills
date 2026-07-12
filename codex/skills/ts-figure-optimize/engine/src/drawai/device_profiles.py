from __future__ import annotations

from dataclasses import dataclass


LOCAL_DEVICE_CHOICES = ("cpu", "gpu", "mps", "auto")
DEFAULT_LOCAL_DEVICE = "cpu"


@dataclass(frozen=True)
class LocalDeviceProfile:
    sam3_device: str
    rmbg_device: str
    paddle_device: str


def normalize_local_device(value: str | None) -> str:
    normalized = str(value or DEFAULT_LOCAL_DEVICE).strip().lower()
    if normalized not in LOCAL_DEVICE_CHOICES:
        supported = ", ".join(LOCAL_DEVICE_CHOICES)
        raise ValueError(f"Unsupported DrawAI local device: {value!r}. Use one of: {supported}.")
    return normalized


def local_device_profile(value: str | None) -> LocalDeviceProfile:
    device = normalize_local_device(value)
    if device == "gpu":
        return LocalDeviceProfile(sam3_device="cuda", rmbg_device="cuda", paddle_device="cpu")
    if device == "mps":
        return LocalDeviceProfile(sam3_device="cpu", rmbg_device="mps", paddle_device="cpu")
    if device == "auto":
        return LocalDeviceProfile(sam3_device="auto", rmbg_device="auto", paddle_device="cpu")
    return LocalDeviceProfile(sam3_device="cpu", rmbg_device="cpu", paddle_device="cpu")


def resolve_local_model_devices(
    device: str | None,
    *,
    sam3_device: str = "",
    rmbg_device: str = "",
    paddle_device: str = "",
) -> LocalDeviceProfile:
    profile = local_device_profile(device)
    return LocalDeviceProfile(
        sam3_device=sam3_device or profile.sam3_device,
        rmbg_device=rmbg_device or profile.rmbg_device,
        paddle_device=paddle_device or profile.paddle_device,
    )

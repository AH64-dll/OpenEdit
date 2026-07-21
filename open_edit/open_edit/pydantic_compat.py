"""Pydantic 2.13.4 compatibility shim.

`OperationUnion = Annotated[Union[...], Field(discriminator="kind")]`
is not a BaseModel subclass, so `.model_validate(...)` doesn't work on it.
Use `TypeAdapter` instead. This shim centralizes the workaround.
"""
from pydantic import TypeAdapter  # noqa: F401  (re-exported)


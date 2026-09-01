# Public API stability (1.0)

The supported import path is:

```python
from nuropb_rmq import Session, RpcClient, MeshService, ReconnectPolicy, CONNECTION_LOST
```

Names listed in [`src/nuropb_rmq/api.py`](../../src/nuropb_rmq/api.py) `__all__` are
the **1.0 freeze**. After 1.0.0:

| Change | Version |
|--------|---------|
| Remove or rename a frozen name | **2.0** |
| Add a new public name | 1.x + CHANGELOG |
| Bugfix / compatible behaviour | 1.x patch |

`ReconnectPolicy.fail_outstanding` defaults to `False` (park-and-retry). Set
`True` for the 0.5.x fail-fast path (`CONNECTION_LOST` on disconnect).

Submodules (`nuropb_rmq.patterns.errors`, …) may still be imported; adapters
that previously deep-imported error constants should switch to `nuropb_rmq`.
Deep imports are not the freeze surface.

Snapshot test: `tests/test_api_surface.py`.

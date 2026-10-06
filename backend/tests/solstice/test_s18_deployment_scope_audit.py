"""S14 spawn and deployment scope: boundary audit.

The lease declares its single-host-volume mechanism and OS lock requirement
honestly; unsupported distributed deployment is out of scope by
declaration, not by untested assumption. No services started.
"""
import sys

sys.path.insert(0, "backend")


def test_deployment_scope_declares_mechanism_and_boundary():
    from services import execution_lease as lease

    scope = lease.deployment_scope()
    assert scope["mechanism"].startswith("atomic file create")
    assert "single host" in scope["scope"]
    assert "multi-host" in scope["not_scope"]
    assert scope["multiprocess_safe"] == lease.MULTIPROCESS_SAFE
    assert scope["version"] == lease.LEASE_VERSION


def test_os_file_lock_available_on_supported_hosts():
    import sys

    from services import execution_lease as lease

    if sys.platform in ("linux", "darwin", "win32"):
        assert lease.MULTIPROCESS_SAFE is True
    else:
        assert lease.deployment_scope()["multiprocess_safe"] is False

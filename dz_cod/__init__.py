__version__ = "0.4.0"

# The oldest dz_core this dz_cod works with: dz_cod imports dz_core's setup,
# features, phone and wilaya code. Raise it in the commit that starts using
# something new from dz_core, and release the two together (docs/DEPLOY.md).
DZ_CORE_MIN = "0.4.0"


def version_tuple(version):
	"""'0.12.1' -> (0, 12, 1), so versions compare as numbers."""
	return tuple(int(part) for part in str(version).split(".") if part.isdigit())


def check_dz_core():
	"""A server that updated dz_cod without dz_core fails here with a clear
	message, instead of an ImportError somewhere in the code."""
	import dz_core

	if version_tuple(dz_core.__version__) < version_tuple(DZ_CORE_MIN):
		raise ImportError(
			f"dz_cod {__version__} needs dz_core {DZ_CORE_MIN} or newer, "
			f"this bench has {dz_core.__version__}: update apps/dz_core, then bench migrate"
		)


check_dz_core()

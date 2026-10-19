"""`bench --site <site> dz-cod-features ...`: the old name of dz_core's
`dz-features` command (dz_core/commands.py), kept so scripts written before
the move keep working. Use `dz-features`.
"""

import click
from dz_core.commands import dz_features

dz_cod_features = click.Command(
	"dz-cod-features",
	callback=dz_features.callback,
	params=dz_features.params,
	help="Old name of dz-features (optional features of a client site).",
)

commands = [dz_cod_features]

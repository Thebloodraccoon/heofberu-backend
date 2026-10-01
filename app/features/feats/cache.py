"""Feat cache namespaces."""

# A feat is a ``features`` row (``source_type=FEAT``): every write also stales
# the shared ``features`` listing / by-id reads.
FEAT_CACHE_NAMESPACES = ("feats", "features")

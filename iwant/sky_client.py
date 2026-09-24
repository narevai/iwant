def resolve(value):
    """SkyPilot's client SDK runs against a local API server: most calls
    (sky.launch, sky.status, sky.check, ...) return a request_id string that
    you resolve with sky.get(). Some code paths/versions may instead return
    the real value directly. Handle both without assuming which - this is
    exactly the kind of detail that isn't consistently documented across
    SkyPilot versions.

    Deliberately does NOT swallow sky.get()'s exceptions: if the underlying
    request failed (e.g. the launch it belongs to failed), that failure must
    propagate - a caller that pretended a not-yet-resolved request_id string
    was a real value (an IP, an endpoint, ...) is exactly the bug that made
    `iwant launch` print "Server started." with a request_id as the URL
    after a failed launch."""
    # Imported lazily - `sky`'s own import graph is large (multi-second on a
    # cold cache) and callers like the model picker never need it at all;
    # paying that cost only inside functions that actually talk to SkyPilot
    # keeps commands/prompts that don't need it snappy.
    import sky

    if isinstance(value, str) and hasattr(sky, "get"):
        return sky.get(value)
    return value

def detect_intent(query):
    q = query.lower()

    if "official" in q or "docs" in q or "documentation" in q:
        return "docs"

    return "general"


def detect_product(query):
    q = query.lower()

    if "kafka" in q:
        return "red_hat_streams_for_apache_kafka"

    if "amq" in q or "broker" in q:
        return "red_hat_amq_broker"

    return None

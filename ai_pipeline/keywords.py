"""
keywords.py

Unified Red Hat Product Catalog, Keyword Routing Rules, Case Status Mapping,
and Query Normalization.

Provides:
- Reference PRODUCT_CATALOG structure with associated product keywords.
- Dynamic, catalog-driven query cleaning for Salesforce / Solr / Elastic backends.
- Case status mapping derived from Red Hat support portal dropdowns.
- Keyword lists for investigation, failure diagnosis, and product identification.
"""

from datetime import datetime, timedelta
import re
from typing import Dict, List, Optional, Set
from dateutil.relativedelta import relativedelta

# =====================================================================
# 1. CASE STATUS MAPPING (Red Hat Salesforce Statuses)
# =====================================================================

CASE_STATUS_MAP: Dict[str, List[str]] = {
    "Unassigned": ["unassigned"],
    "Waiting on Customer": ["waiting on customer", "waiting on user", "customer waiting"],
    "Waiting on Owner": ["waiting on owner"],
    "Waiting on Contributor": ["waiting on contributor"],
    "Waiting on Collaboration": ["waiting on collaboration", "waiting on collab"],
    "Waiting on Documentation": ["waiting on documentation", "waiting on docs", "waiting on doc"],
    "Waiting on Engineering": ["waiting on engineering", "waiting on eng", "waiting on dev", "waiting on r&d"],
    "Waiting on 3rd Party Vendor": ["waiting on 3rd party vendor", "waiting on vendor", "waiting on third party"],
    "Waiting on Collaboration - Native": ["waiting on collaboration - native", "waiting on collaboration native"],
    "Waiting on PM": ["waiting on pm", "waiting on product management", "waiting on product manager"],
    "Waiting on QA": ["waiting on qa", "waiting on quality assurance", "waiting on testing"],
    "Waiting on Sales": ["waiting on sales"],
    "Waiting on Translation": ["waiting on translation"],
    "Closed": ["closed", "resolved", "completed", "cancelled", "canceled"],
}

# =====================================================================
# 2. KEYWORDS & PRODUCT CATALOG
# =====================================================================

PRODUCT_CATALOG: Dict[str, Dict[str, List[str]]] = {
    # -----------------------------------------------------------------
    # Integration & Messaging
    # -----------------------------------------------------------------
    "red_hat_streams_for_apache_kafka": {
        "keywords": [
            "kafka",
            "streams",
            "strimzi",
            "kraft",
            "zookeeper",
            "mirrormaker",
            "mirror maker",
            "kafka connect",
            "kafkaconnect",
            "connect",
            "bridge",
        ]
    },
    "red_hat_amq_broker": {
        "keywords": [
            "amq",
            "amq broker",
            "artemis",
            "activemq",
            "active mq",
            "activemqartemis",
        ]
    },
    "red_hat_amq_interconnect": {
        "keywords": [
            "amq interconnect",
            "interconnect",
            "dispatch router",
            "qdrouterd",
        ]
    },
    "camel": {
        "keywords": [
            "camel",
            "camel-k",
            "camel k",
            "camel quarkus",
            "camel-quarkus",
            "camel spring boot",
            "apache camel",
        ]
    },
    "apicurio_registry": {
        "keywords": [
            "apicurio",
            "apicurio registry",
            "registry",
            "schema registry",
            "schemaregistry",
        ]
    },
    "service_registry": {
        "keywords": [
            "service registry",
        ]
    },
    # -----------------------------------------------------------------
    # OpenShift & Cloud Native Platforms
    # -----------------------------------------------------------------
    "openshift_container_platform": {
        "keywords": [
            "openshift",
            "open shift",
            "ocp",
            "cluster",
            "machineconfig",
            "mcp",
            "kubernetes",
            "k8s",
            "crc",
            "codeready containers",
        ]
    },
    "red_hat_openshift_ai": {
        "keywords": [
            "openshift ai",
            "rhods",
            "red hat open shift ai",
            "data science",
            "vllm",
            "model mesh",
            "kserve",
        ]
    },
    "red_hat_openshift_virtualization": {
        "keywords": [
            "openshift virtualization",
            "kubevirt",
            "virt-launcher",
            "virt-ctl",
            "cnv",
            "container native virtualization",
        ]
    },
    "red_hat_openshift_gitops": {
        "keywords": [
            "openshift gitops",
            "argocd",
            "argo cd",
            "gitops",
        ]
    },
    "red_hat_openshift_pipelines": {
        "keywords": [
            "openshift pipelines",
            "tekton",
            "pipeline",
        ]
    },
    "red_hat_openshift_serverless": {
        "keywords": [
            "openshift serverless",
            "knative",
            "eventing",
            "serving",
        ]
    },
    "red_hat_openshift_service_mesh": {
        "keywords": [
            "service mesh",
            "istio",
            "kiali",
            "jaeger",
            "envoy",
        ]
    },
    "red_hat_openshift_data_foundation": {
        "keywords": [
            "openshift data foundation",
            "odf",
            "ocs",
            "rook",
            "ceph",
            "noobaa",
        ]
    },
    # -----------------------------------------------------------------
    # Linux & OS Infrastructure
    # -----------------------------------------------------------------
    "red_hat_enterprise_linux": {
        "keywords": [
            "rhel",
            "red hat enterprise linux",
            "enterprise linux",
            "kernel",
            "systemd",
            "selinux",
            "rpm",
            "dnf",
            "yum",
        ]
    },
    "red_hat_satellite": {
        "keywords": [
            "satellite",
            "foreman",
            "katello",
            "capsule",
            "pulp",
        ]
    },
    # -----------------------------------------------------------------
    # Automation & AI Tools
    # -----------------------------------------------------------------
    "ansible_automation_platform": {
        "keywords": [
            "ansible",
            "ansible automation platform",
            "aap",
            "ansible tower",
            "tower",
            "automation controller",
            "automation hub",
            "playbook",
        ]
    },
    "red_hat_lightspeed": {
        "keywords": [
            "lightspeed",
            "ansible lightspeed",
            "openshift lightspeed",
        ]
    },
    # -----------------------------------------------------------------
    # Runtime & Application Servers
    # -----------------------------------------------------------------
    "jboss_enterprise_application_platform": {
        "keywords": [
            "jboss",
            "eap",
            "jboss eap",
            "wildfly",
            "undertow",
            "hornetq",
        ]
    },
    "red_hat_build_of_quarkus": {
        "keywords": [
            "quarkus",
            "mutiny",
            "panache",
        ]
    },
    "red_hat_single_sign_on": {
        "keywords": [
            "sso",
            "rh-sso",
            "keycloak",
            "red hat single sign-on",
        ]
    },
    # -----------------------------------------------------------------
    # Multicluster Management & Security
    # -----------------------------------------------------------------
    "advanced_cluster_management": {
        "keywords": [
            "acm",
            "advanced cluster management",
            "multicluster",
            "rhacm",
        ]
    },
    "advanced_cluster_security": {
        "keywords": [
            "acs",
            "advanced cluster security",
            "stackrox",
            "rhacs",
        ]
    },
    "red_hat_quay": {
        "keywords": [
            "quay",
            "clair",
            "container registry",
        ]
    },
}

# =====================================================================
# 3. INVESTIGATION & FAILURE KEYWORDS
# =====================================================================

INVESTIGATION_KEYWORDS = [
    # Action / Search Verbs
    "list cases",
    "find cases",
    "search cases",
    "get cases",
    "show cases",
    "list tickets",
    "find tickets",
    "search tickets",
    "list issues",
    "find issues",
    "search issues",
    # Incident / troubleshooting
    "issue after upgrade",
    "problem after upgrade",
    "restart after upgrade",
    "restart after openshift upgrade",
    "restart after open shift upgrade",
    "open shift upgrade",
    "openshift upgrade",
    "unexpected restart",
    "unexpected reboot",
    "pod restart",
    "container restart",
    "crashloop",
    "crashloopbackoff",
    "service disruption",
    # Historical lookup
    "have we seen this",
    "seen this before",
    "similar customer",
    "similar environment",
    "similar incident",
    "find similar",
    "search historical",
    "historical cases",
    "recurring issue",
    "known issue",
    # RCA
    "root cause",
    "root cause analysis",
    "why did this happen",
    "what caused",
    "identify cause",
    "determine cause",
    # Trend analysis
    "recurring",
    "pattern",
    "patterns",
    "trend",
    "common issue",
    "common failure",
    "engineering pattern",
]

FAILURE_KEYWORDS = [
    # Restarts / crashes
    "restart",
    "crash",
    "crashloop",
    "crashloopbackoff",
    "failed",
    "failure",
    "error",
    "exception",
    "timeout",
    "oom",
    "out of memory",
    # JVM diagnostics
    "heap dump",
    "heapdump",
    "thread dump",
    "threaddump",
    "jvm dump",
    "java dump",
    "javacore",
    "jstack",
    "jmap",
    "memory leak",
    "thread leak",
    "deadlock",
    "gc overhead",
    "gc pause",
    "stack trace",
    "hs_err",
    # Kubernetes / OpenShift
    "pod restart",
    "container restart",
    "not starting",
    "stuck",
    "terminated",
]

# Conversational, structural, & time-expression stop words to scrub from free-text Solr 'q'
SEARCH_STOP_WORDS = {
    "list", "show", "find", "get", "search", "top", "cases", "tickets", "issues",
    "long", "running", "pending", "open", "active", "unresolved", "ongoing",
    "recent", "latest", "first", "last", "me", "the", "a", "an", "for", "in", "of",
    "from", "more", "than", "over", "past", "older", "day", "days", "week", "weeks",
    "month", "months", "year", "years", "ago", "since"
}

# =====================================================================
# 4. DYNAMIC QUERY CLEANING & NORMALIZATION
# =====================================================================


def _build_normalization_map() -> Dict[str, str]:
    """Constructs phrase replacements for search query normalization."""
    return {
        "open shift": "openshift",
        "red hat open shift": "openshift",
        "active mq": "activemq",
        "mirror maker": "mirrormaker",
        "kafka connect": "kafkaconnect",
        "schema registry": "schemaregistry",
        "camel quarkus": "camelquarkus",
        "argo cd": "argocd",
        "ansible tower": "ansible",
        "rh-sso": "keycloak",
        "amq artemis": "amq broker",
        "activemq artemis": "amq broker",
        "artemis": "amq broker",
    }


NORMALIZATION_MAP: Dict[str, str] = _build_normalization_map()


# Replace clean_query_for_search in keywords.py
def clean_query_for_search(query: str) -> str:
    """
    Cleans user query strings for Solr endpoints.
    Strips relative date phrases, conversational stop words, and non-alphanumeric
    characters to prevent Solr/Jetty URL parsing errors.
    """
    if not query:
        return "*:*"

    q = query.lower().strip()

    # 1. Strip relative date expression patterns (e.g. "from more than 2 months")
    q = re.sub(
        r"(?:from\s+)?(?:more\s+than|older\s+than|over|past)\s+\d+\s+(?:day|week|month|year)s?",
        "",
        q,
    )

    # 2. Apply normalization alias mappings
    sorted_aliases = sorted(NORMALIZATION_MAP.keys(), key=len, reverse=True)
    for phrase in sorted_aliases:
        replacement = NORMALIZATION_MAP[phrase]
        pattern = r"\b" + re.escape(phrase) + r"\b"
        q = re.sub(pattern, replacement, q)

    # 3. Remove non-alphanumeric/non-space characters (prevents bad URL characters)
    q = re.sub(r"[^\w\s\-]", " ", q)

    # 4. Extract tokens and filter out stop words and pure digits
    raw_words = re.findall(r"\b[a-zA-Z0-9_\-\.]+\b", q)
    filtered_words = [
        w for w in raw_words
        if w not in SEARCH_STOP_WORDS and not w.isdigit()
    ]

    # 5. Deduplicate adjacent tokens
    deduped_words: List[str] = []
    for i, word in enumerate(filtered_words):
        if i == 0 or word != filtered_words[i - 1]:
            deduped_words.append(word)

    cleaned_query = " ".join(deduped_words)
    return cleaned_query if cleaned_query else "*:*"


def extract_product(query: str) -> Optional[str]:
    """Matches input query against PRODUCT_CATALOG to detect canonical product key."""
    if not query:
        return None

    q = query.lower()

    for product_id, metadata in PRODUCT_CATALOG.items():
        for kw in metadata.get("keywords", []):
            pattern = r"\b" + re.escape(kw.lower()) + r"\b"
            if re.search(pattern, q):
                return product_id

    return None


def is_investigation_query(query: str) -> bool:
    """Checks if user input contains investigation or incident lookup intent."""
    if not query:
        return False

    q = query.lower()

    for kw in INVESTIGATION_KEYWORDS:
        pattern = r"\b" + re.escape(kw.lower()) + r"\b"
        if re.search(pattern, q):
            return True

    return False


def extract_status_filter(query: str) -> Optional[str]:
    """
    Parses specific case statuses or general open/closed intent from the query.
    Matches phrases against CASE_STATUS_MAP and returns a Solr `fq` clause.
    """
    if not query:
        return None

    q = query.lower()

    # 1. Match specific explicit statuses (longest phrase first)
    matched_statuses = []
    for exact_status, phrases in CASE_STATUS_MAP.items():
        if exact_status == "Closed":
            continue
        for phrase in sorted(phrases, key=len, reverse=True):
            pattern = r"\b" + re.escape(phrase) + r"\b"
            if re.search(pattern, q):
                matched_statuses.append(exact_status)
                break

    if matched_statuses:
        if len(matched_statuses) == 1:
            return f'status:"{matched_statuses[0]}"'
        joined_statuses = " OR ".join([f'"{s}"' for s in matched_statuses])
        return f"status:({joined_statuses})"

    # 2. General open/active/pending intent -> Explicitly filter for operational statuses
    open_pattern = r"(?i)\b(waiting|open|active|unresolved|ongoing|in\s+progress|pending|long\s+running)\b"
    if re.search(open_pattern, q):
        return 'status:("Waiting on Owner" OR "Waiting on Customer" OR "Waiting on Red Hat" OR "Waiting on Engineering")'

    return None


def extract_date_filter(query: str) -> dict:
    """
    Extracts relative date constraints dynamically without hardcoding values.
    Defaults to CreatedDate <= 1 month ago if 'long running' or 'pending' is present without a duration.
    Returns ISO 8601 formatted timestamp and target field.
    """
    q = query.lower()

    match = re.search(
        r"(?:from\s+)?(?:more\s+than|older\s+than|over|past)\s+(\d+)\s+(day|week|month|year)s?", q
    )

    amount = None
    unit = None
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
    elif re.search(r"\b(long\s+running|pending)\b", q):
        amount = 1
        unit = "month"
    else:
        return {}

    now = datetime.utcnow()

    if unit == "day":
        target_date = now - timedelta(days=amount)
    elif unit == "week":
        target_date = now - timedelta(weeks=amount)
    elif unit == "month":
        target_date = now - relativedelta(months=amount)
    elif unit == "year":
        target_date = now - relativedelta(years=amount)
    else:
        return {}

    iso_timestamp = target_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    field_name = "CreatedDate"
    if ("updated" in q or "modified" in q) and not re.search(r"\b(long\s+running|pending)\b", q):
        field_name = "LastModifiedDate"

    return {"field": field_name, "operator": "<=", "value": iso_timestamp}

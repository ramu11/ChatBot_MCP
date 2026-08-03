"""
keywords.py

Unified Red Hat Product Catalog, Keyword Routing Rules, and Dynamic Query Normalization.

Provides:
- Reference PRODUCT_CATALOG structure with associated product keywords.
- Dynamic, catalog-driven query cleaning for Salesforce / Solr / Elastic backends.
- Keyword lists for investigation, failure diagnosis, and product identification.
"""

import re
from typing import Dict, List, Optional, Set

# =====================================================================
# 1. KEYWORDS & PRODUCT CATALOG
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
# 2. INVESTIGATION & FAILURE KEYWORDS
# =====================================================================

INVESTIGATION_KEYWORDS = [
    # Action / Search Verbs (Added to support plural search queries)
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

# =====================================================================
# 3. DYNAMIC QUERY CLEANING & NORMALIZATION
# =====================================================================


def _build_normalization_map() -> Dict[str, str]:
    """
    Constructs phrase replacements for search query normalization.
    Only maps specific spaced misspellings or aliases to canonical search terms.
    """
    norm_map: Dict[str, str] = {
        # Fix split product names
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
        # Map sub-variants to canonical terms
        "amq artemis": "amq broker",
        "activemq artemis": "amq broker",
        "artemis": "amq broker",
    }
    return norm_map


NORMALIZATION_MAP: Dict[str, str] = _build_normalization_map()


def clean_query_for_search(query: str) -> str:
    """
    Cleans user query strings for Solr/Salesforce search endpoints:
    1. Replaces aliases with standard product terms using word boundaries.
    2. Deduplicates adjacent identical words (e.g., 'broker broker' -> 'broker').
    3. Preserves natural phrasing so Solr's native scoring works effectively.
    """
    if not query:
        return ""

    q = query.lower().strip()

    # Sort aliases by phrase length descending to prevent partial match collisions
    sorted_aliases = sorted(NORMALIZATION_MAP.keys(), key=len, reverse=True)

    for phrase in sorted_aliases:
        replacement = NORMALIZATION_MAP[phrase]
        pattern = r"\b" + re.escape(phrase) + r"\b"
        q = re.sub(pattern, replacement, q)

    # Deduplicate adjacent duplicate words (e.g., "amq broker broker" -> "amq broker")
    raw_words = re.findall(r"\b[a-zA-Z0-9_\-\.]+\b", q)
    deduped_words: List[str] = []

    for i, word in enumerate(raw_words):
        if i == 0 or word != raw_words[i - 1]:
            deduped_words.append(word)

    cleaned_query = " ".join(deduped_words)
    return cleaned_query if cleaned_query else query.strip()


def extract_product(query: str) -> Optional[str]:
    """
    Matches input query against PRODUCT_CATALOG to detect canonical product key.
    """
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
    """
    Checks if user input contains investigation or incident lookup intent.
    """
    if not query:
        return False

    q = query.lower()

    for kw in INVESTIGATION_KEYWORDS:
        pattern = r"\b" + re.escape(kw.lower()) + r"\b"
        if re.search(pattern, q):
            return True

    return False

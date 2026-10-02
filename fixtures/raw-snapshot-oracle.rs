//! Consumer-owned raw redb migration oracle. It never uses converter helpers.
use redb::{
    ReadOnlyDatabase, ReadableDatabase as _, ReadableTable as _, TableDefinition, TableHandle as _,
};
use rkyv::rancor::Error;
use serde_json::{json, Value};
use sha2::{Digest as _, Sha256};
use std::collections::BTreeSet;

#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
struct OldConfigurationRow {
    state: nexus::ConfigurationState<old_signal::LojixNexusConfiguration>,
}
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
struct NewConfigurationRow {
    state: nexus::ConfigurationState<new_signal::LojixNexusConfiguration>,
}

const DOMAIN: [(&str, &str); 12] = [
    ("live-set", "LiveSetFamily/1"),
    ("gc-roots", "GcRootsFamily/2"),
    ("event-log", "EventLogFamily/3"),
    ("container-lifecycle", "ContainerLifecycleFamily/4"),
    ("deploy-job", "DeployJobFamily/5"),
    ("test-run", "TestRunFamily/6"),
    ("deployment-record", "DeploymentRecordFamily/7"),
    ("identifier-allocation", "IdentifierAllocationFamily/8"),
    ("deployment-outbox", "DeploymentOutboxFamily/9"),
    (
        "pending-transition-intent",
        "PendingTransitionIntentFamily/11",
    ),
    ("nexus-configuration", "NexusConfigurationFamily/12"),
    ("quarantined-row", "QuarantinedRowFamily/13"),
];
const ENGINE_BYTES: [&str; 13] = [
    "__sema_engine_catalog",
    "__sema_engine_counters",
    "__sema_headers",
    "__sema_engine_chain_head",
    "__sema_engine_versioning_policy",
    "__sema_engine_compaction_intent",
    "__sema_engine_staging_slot",
    "__sema_engine_mirror_cursor",
    "__sema_engine_commit_log",
    "__sema_engine_versioned_commit_log",
    "__sema_engine_subscriptions",
    "__sema_engine_checkpoints",
    "__sema_engine_outbox",
];
const ENGINE_U64_KEY_BYTES: [&str; 5] = [
    "__sema_engine_commit_log",
    "__sema_engine_versioned_commit_log",
    "__sema_engine_subscriptions",
    "__sema_engine_checkpoints",
    "__sema_engine_outbox",
];
const ENGINE_U64_VALUE: [&str; 2] = ["__sema_meta", "__sema_engine_identified_counters"];
const ENGINE_HASH_KEY: &str = "__sema_engine_checkpoint_segments";

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}
fn hash(b: &[u8]) -> String {
    format!("{:x}", Sha256::digest(b))
}
fn table_hash(name: &str, rows: &[(Vec<u8>, Vec<u8>)]) -> String {
    let mut h = Sha256::new();
    h.update(b"LojixV5V6Migration/1/table\0");
    h.update((name.len() as u64).to_be_bytes());
    h.update(name.as_bytes());
    for (k, v) in rows {
        h.update((k.len() as u64).to_be_bytes());
        h.update(k);
        h.update((v.len() as u64).to_be_bytes());
        h.update(v);
    }
    format!("{:x}", h.finalize())
}
fn report(name: &str, mut rows: Vec<(Vec<u8>, Vec<u8>)>) -> Value {
    rows.sort_by(|a, b| a.0.cmp(&b.0));
    let records = rows
        .iter()
        .map(|(k, v)| json!({"key_hex":hex(k),"value_sha256":hash(v),"value_bytes":v.len()}))
        .collect::<Vec<_>>();
    json!({"table":name,"rows":rows.len(),"sha256":table_hash(name,&rows),"records":records})
}
fn catalog_report(rows: Vec<(Vec<u8>, Vec<u8>)>) -> Value {
    let mut result = report("__sema_engine_catalog", rows.clone());
    let identities=rows.iter().map(|(key,value)|{let registration=rkyv::from_bytes::<sema_engine::TableRegistration,Error>(value).expect("catalog registration"); let table=registration.table_name(); assert_eq!(key.as_slice(),table.as_bytes(),"catalog raw key/table identity"); json!({"table":table,"family":registration.identity().family().as_str(),"schema_hash_hex":hex(registration.identity().schema_hash().bytes())})}).collect::<Vec<_>>();
    result["identities"] = json!(identities);
    result
}
fn counters_report(rows: Vec<(Vec<u8>, Vec<u8>)>) -> Value {
    let mut canonical = Vec::new();
    let numeric = rows
        .iter()
        .map(|(key, value)| {
            let number = rkyv::from_bytes::<u64, Error>(value).expect("archived engine counter");
            canonical.push((key.clone(), number.to_le_bytes().to_vec()));
            json!({"key":String::from_utf8(key.clone()).expect("counter UTF-8 key"),"value":number})
        })
        .collect::<Vec<_>>();
    let mut result = report("__sema_engine_counters", rows);
    result["numeric"] = json!(numeric);
    result["numeric_sha256"] = json!(table_hash("__sema_engine_counters", &canonical));
    result
}
fn string_bytes(db: &ReadOnlyDatabase, n: &str) -> Result<Vec<(Vec<u8>, Vec<u8>)>, String> {
    let tx = db.begin_read().map_err(|e| e.to_string())?;
    let t = tx
        .open_table(TableDefinition::<String, &[u8]>::new(n))
        .map_err(|e| e.to_string())?;
    t.iter()
        .map_err(|e| e.to_string())?
        .map(|r| {
            let (k, v) = r.map_err(|e| e.to_string())?;
            Ok((k.value().as_bytes().to_vec(), v.value().to_vec()))
        })
        .collect()
}
fn str_bytes(db: &ReadOnlyDatabase, n: &str) -> Result<Vec<(Vec<u8>, Vec<u8>)>, String> {
    let tx = db.begin_read().map_err(|e| e.to_string())?;
    let t = tx
        .open_table(TableDefinition::<&str, &[u8]>::new(n))
        .map_err(|e| e.to_string())?;
    t.iter()
        .map_err(|e| e.to_string())?
        .map(|r| {
            let (k, v) = r.map_err(|e| e.to_string())?;
            Ok((k.value().as_bytes().to_vec(), v.value().to_vec()))
        })
        .collect()
}
fn u64_bytes(db: &ReadOnlyDatabase, n: &str) -> Result<Vec<(Vec<u8>, Vec<u8>)>, String> {
    let tx = db.begin_read().map_err(|e| e.to_string())?;
    let t = tx
        .open_table(TableDefinition::<u64, &[u8]>::new(n))
        .map_err(|e| e.to_string())?;
    t.iter()
        .map_err(|e| e.to_string())?
        .map(|r| {
            let (k, v) = r.map_err(|e| e.to_string())?;
            Ok((k.value().to_le_bytes().to_vec(), v.value().to_vec()))
        })
        .collect()
}
fn str_u64(
    db: &ReadOnlyDatabase,
    n: &str,
    string: bool,
) -> Result<Vec<(Vec<u8>, Vec<u8>)>, String> {
    let tx = db.begin_read().map_err(|e| e.to_string())?;
    if string {
        let t = tx
            .open_table(TableDefinition::<String, u64>::new(n))
            .map_err(|e| e.to_string())?;
        t.iter()
            .map_err(|e| e.to_string())?
            .map(|r| {
                let (k, v) = r.map_err(|e| e.to_string())?;
                Ok((
                    k.value().as_bytes().to_vec(),
                    v.value().to_le_bytes().to_vec(),
                ))
            })
            .collect()
    } else {
        let t = tx
            .open_table(TableDefinition::<&str, u64>::new(n))
            .map_err(|e| e.to_string())?;
        t.iter()
            .map_err(|e| e.to_string())?
            .map(|r| {
                let (k, v) = r.map_err(|e| e.to_string())?;
                Ok((
                    k.value().as_bytes().to_vec(),
                    v.value().to_le_bytes().to_vec(),
                ))
            })
            .collect()
    }
}
fn hash_key(db: &ReadOnlyDatabase, n: &str) -> Result<Vec<(Vec<u8>, Vec<u8>)>, String> {
    let tx = db.begin_read().map_err(|e| e.to_string())?;
    let t = tx
        .open_table(TableDefinition::<&[u8; 32], &[u8]>::new(n))
        .map_err(|e| e.to_string())?;
    t.iter()
        .map_err(|e| e.to_string())?
        .map(|r| {
            let (k, v) = r.map_err(|e| e.to_string())?;
            Ok((k.value().to_vec(), v.value().to_vec()))
        })
        .collect()
}
fn old_router(h: &old_horizon::HorizonDefinition) -> Vec<Value> {
    h.horizon_configuration.generic_nodes.iter().chain(h.cluster_definition.cluster_nodes.iter()).map(|n|match &n.node_network.router_interfaces_option{None=>json!({"node":n.node_name,"router":null}),Some(r)=>json!({"node":n.node_name,"first_interface":r.first_interface,"second_interface":r.second_interface,"wlan_band":format!("{:?}",r.wlan_band),"integer":r.integer,"wlan_standard":format!("{:?}",r.wlan_standard),"secret_reference_option":format!("{:?}",r.secret_reference_option),"backup_wireless_option":format!("{:?}",r.backup_wireless_option),"country_code":r.country_code})}).collect()
}
fn new_router(h: &new_horizon::HorizonDefinition) -> Vec<Value> {
    h.horizon_configuration.generic_nodes.iter().chain(h.cluster_definition.cluster_nodes.iter()).map(|n|match &n.node_network.router_interfaces_option{None=>json!({"node":n.node_name,"router":null}),Some(r)=>json!({"node":n.node_name,"interface":r.interface,"wlan_band":format!("{:?}",r.wlan_band),"integer":r.integer,"wlan_standard":format!("{:?}",r.wlan_standard),"secret_reference_option":format!("{:?}",r.secret_reference_option),"backup_wireless_option":format!("{:?}",r.backup_wireless_option),"country_code":r.country_code})}).collect()
}
fn old_job_routers(v: &old::runtime_model::DeployJob) -> Vec<Value> {
    match &v.optional_deploy_submission {
        Some(old::runtime_model::DeploySubmission::Host(d)) => d
            .horizon_definition_option
            .as_ref()
            .map(old_router)
            .unwrap_or_default(),
        Some(old::runtime_model::DeploySubmission::UserEnvironment(d)) => d
            .horizon_definition_option
            .as_ref()
            .map(old_router)
            .unwrap_or_default(),
        None => Vec::new(),
    }
}
fn new_job_routers(v: &new::runtime_model::DeployJob) -> Vec<Value> {
    match &v.optional_deploy_submission {
        Some(new::runtime_model::DeploySubmission::Host(d)) => d
            .horizon_definition_option
            .as_ref()
            .map(new_router)
            .unwrap_or_default(),
        Some(new::runtime_model::DeploySubmission::UserEnvironment(d)) => d
            .horizon_definition_option
            .as_ref()
            .map(new_router)
            .unwrap_or_default(),
        None => Vec::new(),
    }
}
fn old_semantic(name: &str, data: &[u8]) -> Value {
    if name == "deploy-job" {
        let v =
            rkyv::from_bytes::<old::runtime_model::DeployJob, Error>(data).expect("old deploy-job");
        return json!({"typed_debug":format!("{:?}",v),"routers":old_job_routers(&v)});
    }
    let r = rkyv::from_bytes::<OldConfigurationRow, Error>(data).expect("old configuration");
    let complete = format!("{:?}", r.state);
    let c = r.state.desired_configuration;
    let routers = match c.test_defaults_choice {
        old_signal::TestDefaultsChoice::NoTestDefaults => Vec::new(),
        old_signal::TestDefaultsChoice::TestDefaults(d) => d
            .horizon_definition_option
            .map(|h| old_router(&h))
            .unwrap_or_default(),
    };
    json!({"typed_debug":complete,"desired_key":"desired","ordinary_socket_path":c.ordinary_socket_path,"owner_socket_path":c.owner_socket_path,"state_directory_path":c.state_directory_path,"ordinary_socket_mode":c.ordinary_socket_mode,"owner_socket_mode":c.owner_socket_mode,"daemon_host":c.daemon_host,"meta_configure_occurred":r.state.meta_configure_occurred,"routers":routers})
}
fn new_semantic(name: &str, data: &[u8]) -> Value {
    if name == "deploy-job" {
        let v =
            rkyv::from_bytes::<new::runtime_model::DeployJob, Error>(data).expect("new deploy-job");
        return json!({"typed_debug":format!("{:?}",v),"routers":new_job_routers(&v)});
    }
    let r = rkyv::from_bytes::<NewConfigurationRow, Error>(data).expect("new configuration");
    let complete = format!("{:?}", r.state);
    let c = r.state.desired_configuration;
    let routers = match c.test_defaults_choice {
        new_signal::TestDefaultsChoice::NoTestDefaults => Vec::new(),
        new_signal::TestDefaultsChoice::TestDefaults(d) => d
            .horizon_definition_option
            .map(|h| new_router(&h))
            .unwrap_or_default(),
    };
    json!({"typed_debug":complete,"desired_key":"desired","ordinary_socket_path":c.ordinary_socket_path,"owner_socket_path":c.owner_socket_path,"state_directory_path":c.state_directory_path,"ordinary_socket_mode":c.ordinary_socket_mode,"owner_socket_mode":c.owner_socket_mode,"daemon_host":c.daemon_host,"meta_configure_occurred":r.state.meta_configure_occurred,"routers":routers})
}
fn main() {
    let mut a = std::env::args();
    let p = a.next().unwrap();
    assert_eq!(
        a.next().as_deref(),
        Some("SNAPSHOT"),
        "usage: {p} SNAPSHOT /absolute/store.db"
    );
    let path = a.next().expect("store path");
    assert!(a.next().is_none(), "unexpected argument");
    let schema = std::env::var("LOJIX_ORACLE_SCHEMA").expect("LOJIX_ORACLE_SCHEMA is old or new");
    assert!(
        schema == "old" || schema == "new",
        "LOJIX_ORACLE_SCHEMA is old or new"
    );
    let db = ReadOnlyDatabase::open(&path).expect("open existing store read-only");
    let tx = db.begin_read().expect("begin read");
    let physical = tx
        .list_tables()
        .expect("list physical tables")
        .map(|e| e.name().to_string())
        .collect::<BTreeSet<_>>();
    assert!(
        tx.list_multimap_tables()
            .expect("list multimaps")
            .next()
            .is_none(),
        "multimap physical table is forbidden"
    );
    let allowed = DOMAIN
        .iter()
        .map(|(n, _)| n.to_string())
        .chain(ENGINE_BYTES.map(str::to_string))
        .chain(ENGINE_U64_VALUE.map(str::to_string))
        .chain(std::iter::once(ENGINE_HASH_KEY.to_string()))
        .collect::<BTreeSet<_>>();
    assert!(
        physical.is_subset(&allowed),
        "unknown physical table: {:?}",
        physical.difference(&allowed).collect::<Vec<_>>()
    );
    for n in [
        "__sema_engine_catalog",
        "__sema_engine_counters",
        "__sema_meta",
    ] {
        assert!(
            physical.contains(n),
            "mandatory catalog/metadata table missing: {n}"
        );
    }
    let mut families = Vec::new();
    for (n, id) in DOMAIN {
        let absent = !physical.contains(n);
        let rows = if absent {
            Vec::new()
        } else {
            string_bytes(&db, n).unwrap_or_else(|e| panic!("read {n}: {e}"))
        };
        let semantic = if !absent && (n == "deploy-job" || n == "nexus-configuration") {
            Some(
                rows.iter()
                    .map(|(_, v)| {
                        if schema == "old" {
                            old_semantic(n, v)
                        } else {
                            new_semantic(n, v)
                        }
                    })
                    .collect::<Vec<_>>(),
            )
        } else {
            None
        };
        let mut r = report(n, rows);
        r["identity"] = json!(id);
        r["physically_absent"] = json!(absent);
        if let Some(value) = semantic {
            r["semantic"] = json!(value);
        }
        families.push(r);
    }
    let mut engine = Vec::new();
    for n in ENGINE_BYTES {
        if physical.contains(n) {
            let rows = if ENGINE_U64_KEY_BYTES.contains(&n) {
                u64_bytes(&db, n)
            } else {
                str_bytes(&db, n)
            }
            .unwrap_or_else(|e| panic!("read {n}: {e}"));
            engine.push(if n == "__sema_engine_catalog" {
                catalog_report(rows)
            } else if n == "__sema_engine_counters" {
                counters_report(rows)
            } else {
                report(n, rows)
            });
        }
    }
    for n in ENGINE_U64_VALUE {
        if physical.contains(n) {
            engine.push(report(
                n,
                str_u64(&db, n, n == "__sema_engine_identified_counters")
                    .unwrap_or_else(|e| panic!("read {n}: {e}")),
            ));
        }
    }
    if physical.contains(ENGINE_HASH_KEY) {
        engine.push(report(
            ENGINE_HASH_KEY,
            hash_key(&db, ENGINE_HASH_KEY)
                .unwrap_or_else(|e| panic!("read {ENGINE_HASH_KEY}: {e}")),
        ));
    }
    println!(
        "{}",
        json!({"schema":"LojixV5V6Migration/1","snapshot":"raw-redb-v1","physical_tables":physical,"families":families,"engine_tables":engine})
    );
}

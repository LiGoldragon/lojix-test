//! Consumer-owned fixture driver copied into the immutable converter build tree.
//! It creates only a disposable synthetic v5 store and matching public archives.
use old::Payload as _;
use old::runtime_model as o;
use old::{DeploymentLedger as _, DurableStore as _, EventHistory as _};
use old::{GenerationLedger as _, IdentifierAllocating as _, LegacyConfigurationArchivable as _};
use old::{NexusPersistable as _, Store, TestRunLedger as _};
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
#[path = "qualification-variants.rs"]
mod qualification_variants;

fn old_horizon() -> old_horizon::HorizonDefinition { use old_horizon::*; let hardware = Hardware { integer:4, model_name_option:None, mother_board_option:None, first_integer_option:None, second_integer_option:None, location_option:None }; let machine = || MachineDefinition::Metal(Metal_Data { architecture:Architecture::X86_64, hardware:hardware.clone() }); let keys = || NodeKeys { ssh_pub_key:"ssh-ed25519 AAAAfixture".into(), nix_pub_key_option:None, yggdrasil_key_option:None }; let base = |name: &str, router_interfaces_option| NodeDefinition { node_name:name.into(), node_variant:NodeVariant::Live(LiveDefinition {}), first_magnitude:Magnitude::Max, second_magnitude:Magnitude::Max, machine_definition:machine(), node_environment:NodeEnvironment { keyboard:Keyboard::Qwerty, compressed_swap_option:None }, node_network:NodeNetwork { link_local_ip_vector:vec![], node_ip_option:None, wireguard_pub_key_option:None, wireguard_proxy_vector:vec![], router_interfaces_option }, node_keys:keys(), boolean_option:Some(true), capabilities:vec![], fixed_location_option:None }; let router=base("router",Some(RouterInterfaces { first_interface:"wan0".into(), second_interface:"wlan0".into(), wlan_band:WlanBand::FiveG, integer:36, wlan_standard:WlanStandard::Wifi6, secret_reference_option:Some(SecretReference { secret_name:"router-wifi".into() }), backup_wireless_option:Some(BackupWireless { interface:"wlan1".into(), wireless_network_name:"backup".into(), wlan_band:WlanBand::TwoG, integer:1, wlan_standard:WlanStandard::Wifi4, secret_reference:SecretReference { secret_name:"backup-wifi".into() } }), country_code:"MX".into() })); HorizonDefinition { horizon_configuration:HorizonConfiguration { generic_nodes:vec![], domain_configuration:DomainConfiguration { string:"criome".into(), domain_name_vector:vec![] } }, cluster_definition:ClusterDefinition { cluster_name:"alpha".into(), cluster_nodes:vec![router,base("leaf",None)], generic_node_names:vec![], users:vec![], domains:vec![], cluster_trust:ClusterTrust { magnitude:Magnitude::Max, cluster_trust_entry_vector:vec![], node_trust_entry_vector:vec![], user_trust_entry_vector:vec![] } } } }

fn new_horizon() -> new_horizon::HorizonDefinition { use new_horizon::*; let hardware = Hardware { integer:4, model_name_option:None, mother_board_option:None, first_integer_option:None, second_integer_option:None, location_option:None }; let machine = || MachineDefinition::Metal(Metal_Data { architecture:Architecture::X86_64, hardware:hardware.clone() }); let keys = || NodeKeys { ssh_pub_key:"ssh-ed25519 AAAAfixture".into(), nix_pub_key_option:None, yggdrasil_key_option:None }; let base = |name: &str, router_interfaces_option| NodeDefinition { node_name:name.into(), node_variant:NodeVariant::Live(LiveDefinition {}), first_magnitude:Magnitude::Max, second_magnitude:Magnitude::Max, machine_definition:machine(), node_environment:NodeEnvironment { keyboard:Keyboard::Qwerty, compressed_swap_option:None }, node_network:NodeNetwork { link_local_ip_vector:vec![], node_ip_option:None, wireguard_pub_key_option:None, wireguard_proxy_vector:vec![], router_interfaces_option }, node_keys:keys(), boolean_option:Some(true), capabilities:vec![], fixed_location_option:None }; let router=base("router",Some(RouterInterfaces { interface:"wlan0".into(), wlan_band:WlanBand::FiveG, integer:36, wlan_standard:WlanStandard::Wifi6, secret_reference_option:Some(SecretReference { secret_name:"router-wifi".into() }), backup_wireless_option:Some(BackupWireless { interface:"wlan1".into(), wireless_network_name:"backup".into(), wlan_band:WlanBand::TwoG, integer:1, wlan_standard:WlanStandard::Wifi4, secret_reference:SecretReference { secret_name:"backup-wifi".into() } }), country_code:"MX".into() })); HorizonDefinition { horizon_configuration:HorizonConfiguration { generic_nodes:vec![], domain_configuration:DomainConfiguration { string:"criome".into(), domain_name_vector:vec![] } }, cluster_definition:ClusterDefinition { cluster_name:"alpha".into(), cluster_nodes:vec![router,base("leaf",None)], generic_node_names:vec![], users:vec![], domains:vec![], cluster_trust:ClusterTrust { magnitude:Magnitude::Max, cluster_trust_entry_vector:vec![], node_trust_entry_vector:vec![], user_trust_entry_vector:vec![] } } } }

fn old_horizon_for(mode: &str) -> old_horizon::HorizonDefinition { let mut value = old_horizon(); if mode == "no-router" { value.cluster_definition.cluster_nodes[0].node_network.router_interfaces_option = None; } value }
fn new_horizon_for(mode: &str) -> new_horizon::HorizonDefinition { let mut value = new_horizon(); if mode == "no-router" { value.cluster_definition.cluster_nodes[0].node_network.router_interfaces_option = None; } value }

fn legacy(store: &Path, state: &Path, mode: &str) -> old::LegacyStartupConfiguration {
    old::LegacyStartupConfiguration {
        ordinary_socket_path: state.join("ordinary.sock").display().to_string(), ordinary_socket_mode: 0o660,
        owner_socket_path: state.join("owner.sock").display().to_string(), owner_socket_mode: 0o600,
        state_directory_path: state.display().to_string(), store_path: store.display().to_string(),
        daemon_host: "fixture-daemon".into(), test_defaults: Some(old::TestDefaults { cluster: "alpha".into(), default_vm_host: "leaf".into(), default_mode: old::TestMode::Hermetic, test_flake: "github:fixture/test".into(), test_nix_system: "x86_64-linux".into(), test_output_selector: "checks.fixture".into(), horizon_definition: Some(old_horizon_for(mode)) }),
    }
}
fn admission_identity() -> o::DeploymentRequestIdentity { o::DeploymentRequestIdentity {
    deployment_environment: o::DeploymentEnvironment::HostEnvironment, cluster_name: o::ClusterName::from("fixture-cluster"), node_name: o::NodeName::from("fixture-node"), generation_artifact: o::GenerationArtifact::BaseHost,
    requested_deployment_action: o::RequestedDeploymentAction::Host(o::HostDeployAction::Evaluate), activation_effect: o::ActivationEffect::ProfileOnly, source_revision_policy: o::SourceRevisionPolicy::RequireImmutable,
    optional_immutable_revision: Some(o::ImmutableRevision::from("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")),
} }
fn admission_job() -> o::DeployJob { o::DeployJob {
    deployment_identifier: o::DeploymentIdentifier::new(0), generation_identifier: o::GenerationIdentifier::new(0), cluster_name: o::ClusterName::from("fixture-cluster"), node_name: o::NodeName::from("fixture-node"), deploy_job_phase: o::DeployJobPhase::Submitted, optional_closure_path: None,
    source_revision_policy: o::SourceRevisionPolicy::RequireImmutable, flake_reference: o::FlakeReference::from("github:fixture/old?rev=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"), optional_flake_reference: None, resolved_revision: None,
    deployment_transport: o::DeploymentTransport { nix_store_uri: o::NixStoreUri::from("ssh-ng://fixture-copy.invalid"), ssh_destination: o::SshDestination::from("fixture-login@fixture-activate.invalid") }, deployment_input_mode: o::DeploymentInputMode::Direct,
    deployment_output_selector: o::DeploymentOutputSelector::new(o::FlakeAttribute::from("checks.fixture-a")), activation_backend: o::ActivationBackend::NixosSystemdBootV1, optional_nix_builder_spec: None, boot_once_unit: None, optional_generation_slot: None, persisted_flake_input_override_vector: Vec::new(), deploy_resume_stage: o::DeployResumeStage::ResolveFlakeAuth, optional_phase_receipt: None, optional_deploy_submission: None,
} }
fn horizon_submission(mode: &str) -> o::DeploySubmission { o::DeploySubmission::Host(o::HostDeployment {
    cluster_name: o::ClusterName::from("alpha"), node_name: o::NodeName::from("router"), host_composition: o::HostComposition::BaseHost,
    proposal_source: o::ProposalSource::from("/fixture/horizon.datom"), secrets_input: o::SecretsInput::NoSecrets,
    flake_reference: o::FlakeReference::from("github:fixture/repo?rev=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
    deployment_transport: o::DeploymentTransport { nix_store_uri: o::NixStoreUri::from("ssh-ng://fixture-copy.invalid"), ssh_destination: o::SshDestination::from("fixture@target.invalid") },
    deployment_input_mode: o::DeploymentInputMode::Horizon, horizon_definition_option: Some(old_horizon_for(mode)),
    deployment_output_selector: o::DeploymentOutputSelector::new(o::FlakeAttribute::from("nixosConfigurations.router.config.system.build.toplevel")), activation_backend: o::ActivationBackend::NixosSystemdBootV1,
    host_deploy_action: o::HostDeployAction::ActivateNow, source_revision_policy: o::SourceRevisionPolicy::RequireImmutable,
    optional_nix_builder_spec: None, extra_substituter_vector: Vec::new(),
}) }
fn cache_event(position: u64, cluster: o::ClusterName, node: o::NodeName) -> o::EventLogEntry { o::EventLogEntry {
    event_log_position: o::EventLogPosition::new(position), logged_event: o::LoggedEvent::CacheRetention(o::CacheRetentionTransitionEvent { generation_identifier: o::GenerationIdentifier::new(10), cluster_name: cluster, node_name: node, cache_retention_transition: o::CacheRetentionTransition::Pinned, generation_slot: o::GenerationSlot::Current, optional_generation_slot: None, optional_pin_label: None, event_log_position: o::EventLogPosition::new(position) }),
} }
fn container_event(position: u64, name: &str, state: o::ContainerState, cluster: o::ClusterName, node: o::NodeName) -> (o::ContainerLifecycleRecord, o::EventLogEntry) {
    let record = o::ContainerLifecycleRecord { cluster_name: cluster, node_name: node, container_name: o::ContainerName::from(name), container_state: state, event_log_position: o::EventLogPosition::new(position) };
    let entry = o::EventLogEntry { event_log_position: o::EventLogPosition::new(position), logged_event: o::LoggedEvent::Container(record.clone()) };
    (record, entry)
}
fn main() {
    let args = std::env::args_os().collect::<Vec<_>>();
    let root = args.get(1).map(PathBuf::from).expect("absolute fixture root");
    let mode = args.get(2).and_then(|value| value.to_str()).unwrap_or("rich");
    assert!(root.is_absolute(), "fixture root must be absolute");
    if mode == "verify-old" {
        let rollback_store = root.join("old-rollback/store.db");
        let store = Store::open(&rollback_store).expect("reopen old rollback clone");
        assert_eq!(store.records::<o::LiveGeneration>().expect("rollback live set").len(), 1);
        assert_eq!(store.records::<o::GcRoot>().expect("rollback gc roots").len(), 1);
        assert_eq!(store.records::<o::DeploymentRecord>().expect("rollback deployments").len(), 1);
        assert_eq!(store.records::<o::DeployJob>().expect("rollback retained job").len(), 1);
        assert_eq!(store.records::<o::StoredTestRun>().expect("rollback test run").len(), 1);
        assert_eq!(store.records::<o::ContainerLifecycleRecord>().expect("rollback containers").len(), 2);
        println!("old-store rollback clone reopened with all populated fixture families");
        return;
    }
    let old_state = root.join("old-state"); let destination = root.join("destination");
    assert!(!destination.exists(), "converter destination must be absent"); std::fs::create_dir_all(&old_state).expect("old state");
    let store_path = old_state.join("store.db"); let old_archive = root.join("old-startup.rkyv"); let new_archive = root.join("new-startup.rkyv");
    assert!(matches!(mode, "rich" | "history" | "sparse" | "no-router" | "active-test" | "active-container" | "active-deployment" | "active-intent"), "unknown fixture mode");
    let old_startup = legacy(&store_path, &old_state, mode); old_startup.write_rkyv_file(&old_archive).expect("old archive"); std::fs::set_permissions(&old_archive, std::fs::Permissions::from_mode(0o600)).expect("private old archive");
    let new_startup = new::LegacyStartupConfiguration { ordinary_socket_path: destination.join("ordinary.sock").display().to_string(), ordinary_socket_mode: 0o660, owner_socket_path: destination.join("owner.sock").display().to_string(), owner_socket_mode: 0o600, state_directory_path: destination.display().to_string(), store_path: destination.join("store.db").display().to_string(), daemon_host: "fixture-daemon".into(), test_defaults: Some(new::TestDefaults { cluster: "alpha".into(), default_vm_host: "leaf".into(), default_mode: new::TestMode::Hermetic, test_flake: "github:fixture/test".into(), test_nix_system: "x86_64-linux".into(), test_output_selector: "checks.fixture".into(), horizon_definition: Some(new_horizon_for(mode)) }) };
    use new::LegacyConfigurationArchivable as _; new_startup.write_rkyv_file(&new_archive).expect("new archive"); std::fs::set_permissions(&new_archive, std::fs::Permissions::from_mode(0o600)).expect("private new archive");
    {
        let store = Store::open_with_default_configuration(&store_path, old::NexusConfiguration::from(&old_startup)).expect("old store");
        let meta_state = store.meta_configure(old::NexusConfiguration::from(&old_startup)).expect("synthetic meta configuration");
        assert!(meta_state.meta_configure_occurred, "fixture records its public meta configuration marker");
        if mode != "sparse" {
        let cluster = o::ClusterName::from("fixture-cluster"); let node = o::NodeName::from("fixture-node"); let closure = o::ClosurePath::from("/nix/store/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-fixture");
        store.record_activation(o::LiveGeneration { deployment_identifier: o::DeploymentIdentifier::new(10), generation_identifier: o::GenerationIdentifier::new(10), cluster_name: cluster.clone(), node_name: node.clone(), deployment_environment: o::DeploymentEnvironment::HostEnvironment, generation_artifact: o::GenerationArtifact::BaseHost, activation_effect: o::ActivationEffect::LiveActivation, generation_slot: o::GenerationSlot::Current, closure_path: closure.clone(), source_revision_record: o::SourceRevisionRecord { source_revision_policy: o::SourceRevisionPolicy::RequireImmutable, requested_ref: o::FlakeReference::from("github:fixture/old?rev=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"), resolved_ref: o::FlakeReference::from("github:fixture/old?rev=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"), string: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa".into() } }, o::GcRoot { generation_identifier: o::GenerationIdentifier::new(10), cluster_name: cluster.clone(), node_name: node.clone(), generation_slot: o::GenerationSlot::Current, closure_path: closure.clone(), optional_pin_label: None }).expect("activation");
        let record = store.allocate_deployment_record(admission_identity(), admission_job()).expect("admission"); let deployment_identifier = *record.deployment_identifier.payload();
        let terminal = store.terminalize_deployment(deployment_identifier, o::DeploymentTerminal::Succeeded).expect("terminal acknowledgement");
        let mut retained = admission_job(); retained.deployment_identifier = terminal.deployment_identifier.clone(); retained.generation_identifier = terminal.generation_identifier.clone(); retained.deploy_job_phase = o::DeployJobPhase::Activated; retained.optional_closure_path = Some(closure.clone()); retained.optional_generation_slot = Some(o::GenerationSlot::Current); retained.deploy_resume_stage = o::DeployResumeStage::FinishDeployment; retained.optional_deploy_submission = Some(horizon_submission(mode)); store.upsert_deploy_job(retained).expect("explicit synthetic terminal-job retention");
        store.upsert_test_run(o::StoredTestRun { test_run_identifier: o::TestRunIdentifier::new(1), cluster_name: cluster.clone(), node: node.clone(), host: o::NodeName::from("fixture-host"), test_mode: o::TestMode::Hermetic, test_run_phase: o::TestRunPhase::Completed, test_outcome: o::TestOutcome::Passed, optional_closure_path: Some(o::ClosurePath::from("/nix/store/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-fixture-check")) }).expect("terminal test run");
        for _ in 0..9 { let position = store.allocate_event_log_position().expect("event allocation"); if position == 2 { let (record, entry) = container_event(position, "fixture-container-2", o::ContainerState::Stopped, cluster.clone(), node.clone()); store.record_container_transition(record, entry).expect("stopped container"); } else if position == 10 { let (record, entry) = container_event(position, "fixture-container-10", o::ContainerState::Failed, cluster.clone(), node.clone()); store.record_container_transition(record, entry).expect("failed container"); } else { store.append_event_log_entry(cache_event(position, cluster.clone(), node.clone())).expect("cache event"); } }
        if mode == "history" { qualification_variants::append_history(&store).expect("allocator-backed history"); }
        if mode == "active-test" { qualification_variants::active_test(&store).expect("active public test"); }
        if mode == "active-container" { qualification_variants::active_container(&store).expect("active public container"); }
        if mode == "active-deployment" { qualification_variants::active_deployment(&store, admission_identity(), admission_job()).expect("active public admission"); }
        if mode == "active-intent" { qualification_variants::terminal_pending_intent(&store, admission_identity(), admission_job()).expect("terminal pending intent"); }
        }
    }
    std::fs::set_permissions(&store_path, std::fs::Permissions::from_mode(0o600)).expect("private old store");
    let rollback = root.join("old-rollback"); std::fs::create_dir(&rollback).expect("rollback clone directory"); std::fs::copy(&store_path, rollback.join("store.db")).expect("rollback store clone"); std::fs::copy(&old_archive, rollback.join("startup.rkyv")).expect("rollback archive clone");
    println!("old_archive={} new_archive={} old_store={} destination={} rollback_store={}", old_archive.display(), new_archive.display(), store_path.display(), destination.display(), rollback.join("store.db").display());
}

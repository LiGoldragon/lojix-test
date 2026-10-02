//! Public v5 fixture variants; included by the consumer-owned driver.
use old::runtime_model as o;
use old::{DeploymentLedger as _, EventHistory as _, IdentifierAllocating as _, Payload as _, TestRunLedger as _, TransitionJournal as _};

pub fn append_history(store: &old::Store) -> old::Result<()> {
    for _ in 0..300 {
        let raw = store.allocate_event_log_position()?;
        let position = o::EventLogPosition::new(raw);
        store.append_event_log_entry(o::EventLogEntry {
            event_log_position: position.clone(),
            logged_event: o::LoggedEvent::CacheRetention(o::CacheRetentionTransitionEvent {
                generation_identifier: o::GenerationIdentifier::new(raw + 1), cluster_name: "alpha".into(), node_name: "router".into(),
                cache_retention_transition: o::CacheRetentionTransition::Pinned, generation_slot: o::GenerationSlot::Pinned,
                optional_generation_slot: None, optional_pin_label: None, event_log_position: position,
            }),
        })?;
    }
    Ok(())
}

pub fn active_test(store: &old::Store) -> old::Result<()> {
    store.upsert_test_run(o::StoredTestRun { test_run_identifier:o::TestRunIdentifier::new(99), cluster_name:"alpha".into(), node:"router".into(), host:"leaf".into(), test_mode:o::TestMode::Hermetic, test_run_phase:o::TestRunPhase::Submitted, test_outcome:o::TestOutcome::Pending, optional_closure_path:None })
}

pub fn active_container(store: &old::Store) -> old::Result<()> {
    let raw=store.allocate_event_log_position()?; let position=o::EventLogPosition::new(raw);
    let record=o::ContainerLifecycleRecord { cluster_name:"alpha".into(), node_name:"router".into(), container_name:"fixture-active".into(), container_state:o::ContainerState::Started, event_log_position:position.clone() };
    store.record_container_transition(record.clone(), o::EventLogEntry { event_log_position:position, logged_event:o::LoggedEvent::Container(record) })
}

/// Produces the coupled submitted-job, pending-intent and outbox state through
/// the old durable admission API. Callers supply the same valid public values
/// used by the prepared fixture; no independently fabricated journal row is used.
pub fn active_deployment(
    store: &old::Store,
    identity: o::DeploymentRequestIdentity,
    submitted_job: o::DeployJob,
) -> old::Result<()> {
    let record = store.begin_admission_transition(identity, submitted_job.clone())?;
    let deployment_identifier = *record.deployment_identifier.payload();
    let intent = store.bind_transition_intent(deployment_identifier, 0)?;
    let _ = store.dispatch_transition_intent(&intent)?;
    // Keep the durable journal/outbox unacknowledged while advancing its job via
    // the public ledger API. This isolates the migration's journal guard from
    // its earlier active-job admission guard.
    let mut terminal_job = submitted_job;
    terminal_job.deployment_identifier = record.deployment_identifier.clone();
    terminal_job.generation_identifier = record.generation_identifier.clone();
    terminal_job.deploy_job_phase = o::DeployJobPhase::Activated;
    store.upsert_deploy_job(terminal_job)?;
    Ok(())
}

/// Reproduces the old crash window after a terminal transition persisted its
/// pending intent, before binding an outbox row.
pub fn terminal_pending_intent(store: &old::Store, mut identity: o::DeploymentRequestIdentity, job: o::DeployJob) -> old::Result<()> {
    identity.optional_immutable_revision = Some(o::ImmutableRevision::from("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"));
    let record = store.allocate_deployment_record(identity, job)?;
    store.begin_terminal_transition(*record.deployment_identifier.payload(), o::DeploymentTerminal::Succeeded)?;
    Ok(())
}

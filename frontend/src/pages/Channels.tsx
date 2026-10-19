import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, describe } from "../api";
import { useAuth } from "../auth";
import { Countdown, Empty, ErrorBox, label, PageHeader, Pill, TopicChips, useToast } from "../components";
import type { Channel, Disclosure, PolicyVersion, Visibility } from "../types";

type PolicyDraft = { topics: string[]; max_disclosure: Disclosure; allowed_result_visibility: Visibility[] };

function PolicyFields({ draft, setDraft, published, prefix }: {
  draft: PolicyDraft; setDraft: (d: PolicyDraft) => void; published: string[]; prefix: string;
}) {
  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  return (
    <>
      <fieldset>
        <legend>Topics to publish on this channel (subset of your published topics)</legend>
        {published.map((t) => (
          <label key={t} className="check">
            <input type="checkbox" checked={draft.topics.includes(t)} data-testid={`${prefix}-topic-${t}`}
              onChange={() => setDraft({ ...draft, topics: toggle(draft.topics, t) })} />
            {label(t)}
          </label>
        ))}
      </fieldset>
      <fieldset>
        <legend>Maximum result disclosure</legend>
        {(["score_only", "summary"] as const).map((d) => (
          <label key={d} className="check">
            <input type="radio" name={`${prefix}-disc`} checked={draft.max_disclosure === d}
              onChange={() => setDraft({ ...draft, max_disclosure: d })} data-testid={`${prefix}-disclosure-${d}`} />
            {d === "score_only" ? "Score only" : "Summary"}
          </label>
        ))}
      </fieldset>
      <fieldset>
        <legend>Allowed result visibility</legend>
        {(["requester_only", "both"] as const).map((v) => (
          <label key={v} className="check">
            <input type="checkbox" checked={draft.allowed_result_visibility.includes(v)} data-testid={`${prefix}-visibility-${v}`}
              onChange={() => setDraft({ ...draft, allowed_result_visibility: toggle(draft.allowed_result_visibility, v) })} />
            {v === "both" ? "Both parties" : "Requester only"}
          </label>
        ))}
      </fieldset>
    </>
  );
}

function ChannelCard({ ch }: { ch: Channel }) {
  const { me } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [history, setHistory] = useState(false);
  const [draft, setDraft] = useState<PolicyDraft>({ topics: ch.topics, max_disclosure: ch.max_disclosure,
    allowed_result_visibility: ch.allowed_result_visibility });
  const refresh = () => qc.invalidateQueries({ queryKey: ["my-channels"] });
  const act = useMutation({
    mutationFn: (action: string) => api<Channel>(`/v1/channels/${ch.id}/${action}`, { method: "POST" }),
    onSuccess: (_d, action) => { toast(`Channel ${action}d.`); refresh(); },
    onError: (e) => toast(describe(e), "bad"),
  });
  const save = useMutation({
    mutationFn: () => api<Channel>(`/v1/channels/${ch.id}`, { method: "PATCH", body: { ...draft, expected_policy_version: ch.policy_version } }),
    onSuccess: (c) => {
      toast(`Policy saved as version ${c.policy_version}. Open requests that no longer fit were invalidated.`);
      setEditing(false);
      refresh();
      qc.invalidateQueries({ queryKey: ["inbox"] });
    },
    onError: (e) => toast(describe(e), "bad"),
  });
  const versions = useQuery({
    queryKey: ["policy-versions", ch.id, ch.policy_version],
    queryFn: () => api<{ versions: PolicyVersion[] }>(`/v1/channels/${ch.id}/policy-versions`),
    enabled: history,
  });
  const live = ch.status === "ACTIVE" || ch.status === "PAUSED";
  return (
    <li className="card" data-testid={`my-channel-${ch.id}`}>
      <div className="row between wrap">
        <div className="row wrap">
          <Pill value={ch.status} testId="channel-status" />
          <span className="muted small">policy v{ch.policy_version}</span>
          {ch.expires_at && live && <span className="small">expires in <Countdown until={ch.expires_at} /></span>}
        </div>
        <div className="row wrap">
          {ch.status === "DRAFT" && <button className="primary" onClick={() => act.mutate("activate")} data-testid="activate">Activate (24 h)</button>}
          {ch.status === "ACTIVE" && <button onClick={() => act.mutate("pause")} data-testid="pause">Pause</button>}
          {ch.status === "PAUSED" && <button onClick={() => act.mutate("resume")} data-testid="resume">Resume</button>}
          {live && <button className="danger" onClick={() => act.mutate("close")} data-testid="close">Close</button>}
          {(live || ch.status === "DRAFT") && <button className="ghost" onClick={() => setEditing(!editing)} data-testid="edit-policy">Edit policy</button>}
          <button className="ghost" onClick={() => setHistory(!history)}>History</button>
        </div>
      </div>
      <TopicChips topics={ch.topics} />
      <p className="muted small">
        Audience: verified researchers · visibility: topics only · approval: manual · max disclosure {label(ch.max_disclosure)} ·
        result visibility: {ch.allowed_result_visibility.map(label).join(", ")}
      </p>
      {editing && (
        <form className="scope-form" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <PolicyFields draft={draft} setDraft={setDraft} published={me!.published_topics} prefix={`edit-${ch.id}`} />
          <p className="hint">Tightening applies immediately: pending and approved requests that no longer fit are cancelled, and running comparisons are not released.</p>
          <button className="primary" disabled={draft.topics.length === 0 || draft.allowed_result_visibility.length === 0} data-testid="save-policy">
            Save as version {ch.policy_version + 1}
          </button>
        </form>
      )}
      {history && versions.data && (
        <table>
          <thead><tr><th>Version</th><th>Topics</th><th>Max disclosure</th><th>Result visibility</th><th>Created</th></tr></thead>
          <tbody>
            {versions.data.versions.map((v) => (
              <tr key={v.version}><td>v{v.version}</td><td>{v.topics.map(label).join(", ")}</td><td>{label(v.max_disclosure)}</td>
                <td>{v.allowed_result_visibility.map(label).join(", ")}</td><td>{new Date(v.created_at).toLocaleString()}</td></tr>
            ))}
          </tbody>
        </table>
      )}
    </li>
  );
}

export function Channels() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [draft, setDraft] = useState<PolicyDraft>({ topics: me!.published_topics.slice(0, 2), max_disclosure: "score_only",
    allowed_result_visibility: ["requester_only", "both"] });
  const q = useQuery({ queryKey: ["my-channels"], queryFn: () => api<{ channels: Channel[] }>("/v1/channels/mine"), refetchInterval: 5000 });
  const create = useMutation({
    mutationFn: () => api<Channel>("/v1/channels", { method: "POST", body: draft }),
    onSuccess: () => { toast("Draft channel created. Activate it to start the 24-hour window."); qc.invalidateQueries({ queryKey: ["my-channels"] }); },
    onError: (e) => toast(describe(e), "bad"),
  });
  return (
    <>
      <PageHeader title="My channels">
        Open a channel to let verified researchers find you by published topics and ask for a comparison. Opening a
        channel never grants access to your graph; every comparison needs your manual approval.
      </PageHeader>
      <section className="card">
        <h2>New channel</h2>
        <form className="scope-form" onSubmit={(e) => { e.preventDefault(); create.mutate(); }} data-testid="new-channel">
          <PolicyFields draft={draft} setDraft={setDraft} published={me!.published_topics} prefix="new" />
          <button className="primary" disabled={create.isPending || draft.topics.length === 0} data-testid="create-channel">
            Create draft
          </button>
        </form>
      </section>
      <ErrorBox error={q.error} />
      {q.data && q.data.channels.length === 0 && <Empty>You have no channels yet.</Empty>}
      <ul className="list">{[...(q.data?.channels ?? [])].reverse().map((c) => <ChannelCard key={c.id} ch={c} />)}</ul>
    </>
  );
}

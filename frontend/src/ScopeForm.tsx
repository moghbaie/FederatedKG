import { useMemo, useState } from "react";
import { describe, newIdempotencyKey } from "./api";
import { label, useToast } from "./components";
import type { Disclosure, Scope, Visibility } from "./types";

type Props = {
  allowedTopics: string[];
  maxDisclosure: Disclosure;
  allowedVisibility: Visibility[];
  onSubmit: (body: { scope: Omit<Scope, "normalization">; result_visibility: Visibility; idempotency_key: string }) => Promise<unknown>;
  onDone: () => void;
  testId: string;
};

/** Builds a comparison scope within what the other side's policy allows. */
export function ScopeForm({ allowedTopics, maxDisclosure, allowedVisibility, onSubmit, onDone, testId }: Props) {
  const [topics, setTopics] = useState<string[]>(allowedTopics.slice(0, 1));
  const [classes, setClasses] = useState<("Protein" | "Interaction")[]>(["Protein"]);
  const [metric, setMetric] = useState<"jaccard" | "overlap_count">("jaccard");
  const [disclosure, setDisclosure] = useState<Disclosure>("score_only");
  const [visibility, setVisibility] = useState<Visibility>(allowedVisibility.includes("requester_only") ? "requester_only" : allowedVisibility[0]);
  const [busy, setBusy] = useState(false);
  // One key per form instance: a double-submit returns the same request instead of a duplicate.
  const idempotencyKey = useMemo(newIdempotencyKey, []);
  const toast = useToast();

  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await onSubmit({
        scope: { topics, entity_classes: classes, metric, protocol: "psi_ca", disclosure },
        result_visibility: visibility,
        idempotency_key: idempotencyKey,
      });
      toast("Request sent. The other researcher must approve it manually.");
      onDone();
    } catch (err) {
      toast(describe(err), "bad");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="scope-form" onSubmit={submit} data-testid={testId}>
      <fieldset>
        <legend>Topics in scope</legend>
        {allowedTopics.map((t) => (
          <label key={t} className="check">
            <input type="checkbox" checked={topics.includes(t)} onChange={() => setTopics(toggle(topics, t))}
              data-testid={`scope-topic-${t}`} />
            {label(t)}
          </label>
        ))}
      </fieldset>
      <fieldset>
        <legend>Compare</legend>
        {(["Protein", "Interaction"] as const).map((c) => (
          <label key={c} className="check">
            <input type="checkbox" checked={classes.includes(c)} onChange={() => setClasses(toggle(classes, c))}
              data-testid={`scope-class-${c}`} />
            {c === "Protein" ? "Proteins" : "Interactions"}
          </label>
        ))}
      </fieldset>
      <fieldset>
        <legend>Metric</legend>
        <select value={metric} onChange={(e) => setMetric(e.target.value as typeof metric)}>
          <option value="jaccard">Jaccard similarity</option>
          <option value="overlap_count">Overlap count</option>
        </select>
      </fieldset>
      <fieldset>
        <legend>Result disclosure</legend>
        <label className="check">
          <input type="radio" name={`${testId}-disc`} checked={disclosure === "score_only"} onChange={() => setDisclosure("score_only")} />
          Score only (coarse band)
        </label>
        <label className="check" title={maxDisclosure === "score_only" ? "The owner's policy allows score only" : ""}>
          <input type="radio" name={`${testId}-disc`} disabled={maxDisclosure === "score_only"}
            checked={disclosure === "summary"} onChange={() => setDisclosure("summary")} data-testid="scope-summary" />
          Summary (band + set-size ranges)
        </label>
        <label className="check disabled" title="Evidence sharing is planned for a later release">
          <input type="radio" disabled /> Evidence (not available in v1)
        </label>
      </fieldset>
      <fieldset>
        <legend>Who sees the result</legend>
        {allowedVisibility.map((v) => (
          <label key={v} className="check">
            <input type="radio" name={`${testId}-vis`} checked={visibility === v} onChange={() => setVisibility(v)}
              data-testid={`scope-visibility-${v}`} />
            {v === "both" ? "Both of us" : "Only me"}
          </label>
        ))}
      </fieldset>
      <p className="hint">
        Matching uses PSI-CA: neither side sends its entity list. The other agent learns your set size; the result is a
        coarse band.
      </p>
      <button className="primary" disabled={busy || topics.length === 0 || classes.length === 0} data-testid={`${testId}-submit`}>
        {busy ? "Sending…" : "Send request"}
      </button>
    </form>
  );
}

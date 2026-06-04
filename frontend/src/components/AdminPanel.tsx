/**
 * Admin Panel — accordion wizard for configuring group → model → prompt mappings.
 *
 * Steps:
 *   1. Select Models (multi-select from Foundry)
 *   2. Select Entra Group
 *   3. Enter System Prompt
 *
 * Each step shows a green tick when completed. Next/Submit buttons navigate.
 * On submit, saves to backend (Cosmos DB / in-memory).
 */
import {useCallback, useEffect, useState} from "react";
import toast from "react-hot-toast";
import {authFetch} from "../api";

/* ── Types ──────────────────────────────────────────────────────────── */

interface FoundryModel {
  model_id: string;
  display_name: string;
  provider: string;
  deployed?: boolean;
}

interface EntraGroup {
  group_id: string;
  display_name: string;
  member_count: number;
}

/* ── Component ──────────────────────────────────────────────────────── */

export default function AdminPanel() {
  const [activeStep, setActiveStep] = useState(0);
  const [models, setModels] = useState<FoundryModel[]>([]);
  const [groups, setGroups] = useState<EntraGroup[]>([]);
  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  const [modelsVisibleToUsers, setModelsVisibleToUsers] = useState(true);
  const [selectedGroup, setSelectedGroup] = useState<string>("");
  const [selectedGroupId, setSelectedGroupId] = useState<string>("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  // Fetch models and groups on mount
  useEffect(() => {
    setLoading(true);
    Promise.all([
      authFetch("/api/v1/admin/foundry-models")
        .then((r) => r.json())
        .then(setModels)
        .catch(() => toast.error("Failed to load models")),
      authFetch("/api/v1/admin/entra-groups")
        .then((r) => r.json())
        .then(setGroups)
        .catch(() => toast.error("Failed to load groups")),
    ]).finally(() => setLoading(false));
  }, []);

  const step1Done = selectedModels.length > 0;
  const step2Done = selectedGroup !== "";
  const step3Done = systemPrompt.trim().length > 0;
  const allDone = step1Done && step2Done && step3Done;

  const handleSubmit = useCallback(async () => {
    if (!allDone) return;
    setSaving(true);

    // One document per Entra group: POST a single GroupModelConfig.
    const group = {
      group_name: selectedGroup,
      group_id: selectedGroupId,
      model_ids: selectedModels,
      models_visible_to_users: modelsVisibleToUsers,
      system_prompt: systemPrompt,
    };

    try {
      const res = await authFetch("/api/v1/admin/config/group", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(group),
      });

      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(detail?.detail || `Save failed (HTTP ${res.status})`);
      }
      toast.success("Configuration saved successfully!");
      // Reset for next entry
      setSelectedModels([]);
      setModelsVisibleToUsers(true);
      setSelectedGroup("");
      setSelectedGroupId("");
      setSystemPrompt("");
      setActiveStep(0);
    } catch (err: any) {
      toast.error(err.message || "Failed to save configuration");
    } finally {
      setSaving(false);
    }
  }, [
    allDone,
    selectedModels,
    selectedGroup,
    selectedGroupId,
    systemPrompt,
    modelsVisibleToUsers,
  ]);

  const toggleModel = (id: string) => {
    setSelectedModels((prev) =>
      prev.includes(id) ? prev.filter((m) => m !== id) : [...prev, id],
    );
  };

  const selectGroup = (g: EntraGroup) => {
    setSelectedGroup(g.display_name);
    setSelectedGroupId(g.group_id);
  };

  /* ── Render ─────────────────────────────────────────────────────────── */

  const steps = [
    {label: "Select Models", done: step1Done},
    {label: "Select Entra Group", done: step2Done},
    {label: "System Prompt", done: step3Done},
  ];

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-2xl font-semibold text-text-primary mb-1">
          Admin Configuration
        </h1>
        <p className="text-sm text-text-tertiary mb-8">
          Assign models and system prompts to Entra ID groups
        </p>

        {loading ? (
          <ArupLoader label="Loading models & groups…" />
        ) : (
          /* Accordion Steps */
          <div className="space-y-3">
            {steps.map((step, i) => (
              <div
                key={i}
                className="rounded-2xl border border-border-light bg-surface-card overflow-hidden"
              >
                {/* Step header */}
                <button
                  onClick={() => setActiveStep(activeStep === i ? -1 : i)}
                  className="w-full flex items-center gap-3 px-5 py-4 text-left cursor-pointer hover:bg-surface-hover transition-colors duration-200"
                >
                  {/* Step number / tick */}
                  <div
                    className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold transition-colors duration-200 ${
                      step.done
                        ? "bg-emerald-100 text-emerald-600"
                        : activeStep === i
                          ? "bg-accent text-white"
                          : "bg-surface text-text-tertiary"
                    }`}
                  >
                    {step.done ? <CheckIcon className="w-4 h-4" /> : i + 1}
                  </div>

                  <span
                    className={`flex-1 text-sm font-medium ${
                      step.done ? "text-emerald-700" : "text-text-primary"
                    }`}
                  >
                    {step.label}
                  </span>

                  {/* Chevron */}
                  <svg
                    className={`w-4 h-4 text-text-tertiary transition-transform duration-200 ${
                      activeStep === i ? "rotate-180" : ""
                    }`}
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </button>

                {/* Step content */}
                {activeStep === i && (
                  <div className="px-5 pb-5 border-t border-border-light">
                    {i === 0 && (
                      <Step1Models
                        models={models}
                        selected={selectedModels}
                        onToggle={toggleModel}
                        modelsVisibleToUsers={modelsVisibleToUsers}
                        onToggleVisibility={setModelsVisibleToUsers}
                      />
                    )}
                    {i === 1 && (
                      <Step2Groups
                        groups={groups}
                        selectedId={selectedGroupId}
                        onSelect={selectGroup}
                      />
                    )}
                    {i === 2 && (
                      <Step3Prompt
                        value={systemPrompt}
                        onChange={setSystemPrompt}
                        groupName={selectedGroup}
                        modelIds={selectedModels}
                      />
                    )}

                    {/* Navigation */}
                    <div className="flex justify-between mt-5">
                      {i > 0 ? (
                        <button
                          onClick={() => setActiveStep(i - 1)}
                          className="px-4 py-2 rounded-xl text-sm text-text-secondary hover:bg-surface-hover transition-colors duration-200 cursor-pointer"
                        >
                          Back
                        </button>
                      ) : (
                        <div />
                      )}

                      {i < steps.length - 1 ? (
                        <button
                          onClick={() => setActiveStep(i + 1)}
                          disabled={!steps[i].done}
                          className="px-5 py-2 rounded-xl bg-accent text-white text-sm font-medium hover:bg-accent-hover disabled:opacity-30 disabled:cursor-not-allowed transition-colors duration-200 cursor-pointer"
                        >
                          Next
                        </button>
                      ) : (
                        <button
                          onClick={handleSubmit}
                          disabled={!allDone || saving}
                          className="px-5 py-2 rounded-xl bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors duration-200 cursor-pointer"
                        >
                          {saving ? "Saving…" : "Submit Configuration"}
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Arup-themed loader ─────────────────────────────────────────────── */

function ArupLoader({label}: Readonly<{label?: string}>) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4">
      <div className="relative h-12 w-12">
        {/* Track */}
        <div className="absolute inset-0 rounded-full border-4 border-border-light" />
        {/* Arup-red sweeping arc */}
        <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-accent animate-spin" />
        {/* Pulsing centre dot */}
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="h-2 w-2 rounded-full bg-accent animate-pulse" />
        </div>
      </div>
      {label && (
        <p className="text-sm font-medium text-text-secondary">{label}</p>
      )}
    </div>
  );
}

/* ── Step 1: Multi-select models ────────────────────────────────────── */

function Step1Models({
  models,
  selected,
  onToggle,
  modelsVisibleToUsers,
  onToggleVisibility,
}: Readonly<{
  models: FoundryModel[];
  selected: string[];
  onToggle: (id: string) => void;
  modelsVisibleToUsers: boolean;
  onToggleVisibility: (visible: boolean) => void;
}>) {
  return (
    <div className="pt-4">
      <p className="text-xs text-text-tertiary mb-3">
        Select one or more models from Azure AI Foundry
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {models.map((m) => {
          const isSelected = selected.includes(m.model_id);
          return (
            <button
              key={m.model_id}
              onClick={() => onToggle(m.model_id)}
              className={`flex items-center gap-3 px-4 py-3 rounded-xl border text-left text-sm transition-all duration-200 cursor-pointer ${
                isSelected
                  ? "border-emerald-300 bg-emerald-50 text-emerald-800"
                  : "border-border-light bg-surface hover:bg-surface-hover text-text-primary"
              }`}
            >
              <div
                className={`w-5 h-5 rounded-md border-2 flex items-center justify-center transition-colors duration-200 ${
                  isSelected
                    ? "bg-emerald-500 border-emerald-500"
                    : "border-border bg-white"
                }`}
              >
                {isSelected && <CheckIcon className="w-3 h-3 text-white" />}
              </div>
              <div className="flex-1">
                <span className="font-medium">{m.model_id}</span>
                <span className="block text-[11px] text-text-tertiary">
                  {m.display_name}
                </span>
              </div>
            </button>
          );
        })}
      </div>
      {selected.length > 0 && (
        <p className="text-xs text-emerald-600 mt-3">
          {selected.length} model{selected.length > 1 ? "s" : ""} selected
        </p>
      )}
      <label className="mt-4 flex items-start gap-2 text-xs text-text-secondary cursor-pointer">
        <input
          type="checkbox"
          checked={modelsVisibleToUsers}
          onChange={(e) => onToggleVisibility(e.target.checked)}
          className="mt-0.5 rounded border-border-light text-accent focus:ring-accent"
        />
        <span>
          Show models to end users
          <span className="block text-[11px] text-text-tertiary">
            If unchecked, the model dropdown will display “Auto” and the router
            will pick the best model behind the scenes.
          </span>
        </span>
      </label>
    </div>
  );
}

/* ── Step 2: Select Entra group ─────────────────────────────────────── */

function Step2Groups({
  groups,
  selectedId,
  onSelect,
}: {
  groups: EntraGroup[];
  selectedId: string;
  onSelect: (g: EntraGroup) => void;
}) {
  return (
    <div className="pt-4">
      <p className="text-xs text-text-tertiary mb-3">
        Select the Entra ID group to assign models to
      </p>
      <div className="space-y-2">
        {groups.map((g) => {
          const isSelected = selectedId === g.group_id;
          return (
            <button
              key={g.group_id}
              onClick={() => onSelect(g)}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl border text-left text-sm transition-all duration-200 cursor-pointer ${
                isSelected
                  ? "border-emerald-300 bg-emerald-50 text-emerald-800"
                  : "border-border-light bg-surface hover:bg-surface-hover text-text-primary"
              }`}
            >
              <div
                className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors duration-200 ${
                  isSelected
                    ? "bg-emerald-500 border-emerald-500"
                    : "border-border bg-white"
                }`}
              >
                {isSelected && (
                  <div className="w-2 h-2 bg-white rounded-full" />
                )}
              </div>
              <div className="flex-1">
                <span className="font-medium">{g.display_name}</span>
                <span className="block text-[11px] text-text-tertiary">
                  {g.member_count} members
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ── Step 3: System prompt ──────────────────────────────────────────── */

interface PersonaCard {
  key: string;
  title: string;
  blurb: string;
}

// Suggestion cards. "auto" infers the persona from the selected Entra group;
// "developer" is the 7th persona (builders calling models from their own app).
const PERSONA_CARDS: PersonaCard[] = [
  {
    key: "auto",
    title: "Match Entra Group",
    blurb: "Infer the best persona from the selected group name.",
  },
  {
    key: "casual",
    title: "Casual Opportunistic",
    blurb: "Friendly, simple guidance for light, general use.",
  },
  {
    key: "productivity",
    title: "Productivity Power User",
    blurb: "Structured, thorough output for documents & analysis.",
  },
  {
    key: "leadership",
    title: "Leadership / Decision Support",
    blurb: "Concise, strategic, executive-tone insight.",
  },
  {
    key: "developer",
    title: "Developer / Builder",
    blurb: "Includes recommended model + endpoint for their own app.",
  },
];

interface GeneratedPrompt {
  persona: string;
  persona_label: string;
  prompt: string;
  recommended_model?: string | null;
  endpoint?: string | null;
}

function Step3Prompt({
  value,
  onChange,
  groupName,
  modelIds,
}: Readonly<{
  value: string;
  onChange: (v: string) => void;
  groupName: string;
  modelIds: string[];
}>) {
  const [generatingKey, setGeneratingKey] = useState<string | null>(null);
  const [lastMeta, setLastMeta] = useState<GeneratedPrompt | null>(null);

  const generate = async (card: PersonaCard) => {
    setGeneratingKey(card.key);
    try {
      const res = await authFetch("/api/v1/admin/generate-prompt", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          group_name: groupName,
          model_ids: modelIds,
          persona: card.key === "auto" ? null : card.key,
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(detail?.detail || `HTTP ${res.status}`);
      }
      const data: GeneratedPrompt = await res.json();
      onChange(data.prompt);
      setLastMeta(data);
      toast.success(`Generated for ${data.persona_label}`);
    } catch (err: any) {
      toast.error(err.message || "Failed to generate prompt");
    } finally {
      setGeneratingKey(null);
    }
  };

  return (
    <div className="pt-4">
      <p className="text-xs text-text-tertiary mb-3">
        Pick a suggested persona to generate a starting prompt, then edit it as
        needed. Generation uses the assigned models and the selected Entra group
        {groupName ? ` (${groupName})` : ""}.
      </p>

      {/* Suggestion cards — the "Match Entra Group" card only shows once a group is selected */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-4">
        {PERSONA_CARDS.filter((card) => card.key !== "auto" || groupName).map(
          (card) => {
            const busy = generatingKey === card.key;
            const disabled = generatingKey !== null;
            return (
              <button
                key={card.key}
                onClick={() => generate(card)}
                disabled={disabled}
                className={`group flex items-start gap-3 px-4 py-3 rounded-xl border text-left text-sm transition-all duration-200 cursor-pointer disabled:cursor-not-allowed ${
                  busy
                    ? "border-accent bg-accent/5"
                    : "border-border-light bg-surface hover:bg-surface-hover hover:border-accent/40"
                } ${disabled && !busy ? "opacity-50" : ""}`}
              >
                <span className="mt-0.5 flex-shrink-0 text-accent">
                  {busy ? (
                    <span className="block h-4 w-4 rounded-full border-2 border-accent/30 border-t-accent animate-spin" />
                  ) : (
                    <SparkleIcon className="w-4 h-4" />
                  )}
                </span>
                <span className="flex-1">
                  <span className="font-medium text-text-primary block">
                    {card.title}
                  </span>
                  <span className="block text-[11px] text-text-tertiary">
                    {busy ? "Generating…" : card.blurb}
                  </span>
                </span>
              </button>
            );
          },
        )}
      </div>

      {/* Developer (7th persona) integration hints */}
      {lastMeta?.persona === "developer" &&
        (lastMeta.recommended_model || lastMeta.endpoint) && (
          <div className="mb-4 rounded-xl border border-accent/30 bg-accent/5 px-4 py-3 text-xs text-text-secondary">
            <p className="font-medium text-text-primary mb-1">
              For your own application
            </p>
            {lastMeta.recommended_model && (
              <p>
                Recommended model:{" "}
                <code className="text-accent">
                  {lastMeta.recommended_model}
                </code>
              </p>
            )}
            {lastMeta.endpoint && (
              <p className="break-all">
                Endpoint:{" "}
                <code className="text-accent">{lastMeta.endpoint}</code>
              </p>
            )}
          </div>
        )}

      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="You are a helpful enterprise AI assistant. Be concise, professional, and accurate…"
        className="w-full h-36 px-4 py-3 rounded-xl border border-border-light bg-surface text-sm text-text-primary placeholder:text-text-tertiary resize-none focus:outline-none focus:border-border focus:ring-1 focus:ring-border/20 transition-all duration-200"
      />
      <p className="text-[11px] text-text-tertiary mt-2">
        {value.length} characters
      </p>
    </div>
  );
}

/* ── Sparkle icon ───────────────────────────────────────────────────── */

function SparkleIcon({className}: Readonly<{className?: string}>) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M12 2l1.9 4.8L18.7 8.7 13.9 10.6 12 15.4 10.1 10.6 5.3 8.7l4.8-1.9L12 2zM18 14l.95 2.4L21.35 17.35 18.95 18.3 18 20.7 17.05 18.3 14.65 17.35 17.05 16.4 18 14zM6 14l.95 2.4L9.35 17.35 6.95 18.3 6 20.7 5.05 18.3 2.65 17.35 5.05 16.4 6 14z" />
    </svg>
  );
}

/* ── Check icon ─────────────────────────────────────────────────────── */

function CheckIcon({className}: {className?: string}) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

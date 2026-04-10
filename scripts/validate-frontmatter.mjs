// Deno版バリデータ: npm依存なしで運用対象ドキュメントの front-matter と stale ロジックを検証
import { expandGlob } from "https://deno.land/std@0.208.0/fs/expand_glob.ts";
import { extract } from "https://deno.land/std@0.208.0/front_matter/any.ts";
import { sep } from "https://deno.land/std@0.208.0/path/mod.ts";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const MS_PER_DAY = 1000 * 60 * 60 * 24;
const STALE_DAYS = 30;
const REQUIRED_KEYS = [
	"title",
	"status",
	"draft_status",
	"created_at",
	"updated_at",
	"references",
	"related_issues",
	"related_prs",
];
const STATUS_VALUES = ["proposed", "active", "superseded"];
const DRAFT_STATUS_VALUES = ["idea", "exploring", "paused", "n/a"];

const isStringArray = (val) =>
	Array.isArray(val) && val.every((v) => typeof v === "string");
const isIntegerArray = (val) =>
	Array.isArray(val) && val.every((v) => Number.isInteger(v));
const isNonNegativeInt = (val) => Number.isInteger(val) && val >= 0;

const parseDate = (value) => {
	if (typeof value !== "string" || !DATE_RE.test(value)) return null;
	const d = new Date(`${value}T00:00:00Z`);
	return Number.isNaN(d.getTime()) ? null : d;
};

const diffDays = (from, to) =>
	Math.floor((to.getTime() - from.getTime()) / MS_PER_DAY);
const isInArchives = (path) => path.split(sep).includes("archives");
const isDraftPath = (path) => path.split(sep).includes("draft");
const isInStandards = (path) => path.split(sep).includes("standards");

const loadFrontMatter = async (file) => {
	const src = await Deno.readTextFile(file);
	const { attrs } = extract(src);
	if (!attrs || typeof attrs !== "object") return {};
	return attrs;
};

const run = async () => {
	const errors = [];
	const warnings = [];

	for await (const entry of expandGlob("_docs/**/*.md", { globstar: true })) {
		if (!entry.isFile) continue;
		const file = entry.path;
		if (isInArchives(file)) continue;
		if (isInStandards(file)) continue;

		const data = await loadFrontMatter(file);
		const fileErrors = [];
		const fileWarnings = [];

		for (const key of REQUIRED_KEYS) {
			if (!(key in data)) {
				fileErrors.push(`missing required field: ${key}`);
			}
		}

		const status = data.status;
		const draftStatus = data.draft_status;
		if (status && !STATUS_VALUES.includes(status)) {
			fileErrors.push(`status must be one of ${STATUS_VALUES.join(", ")}`);
		}
		if (draftStatus && !DRAFT_STATUS_VALUES.includes(draftStatus)) {
			fileErrors.push(
				`draft_status must be one of ${DRAFT_STATUS_VALUES.join(", ")}`
			);
		}

		const createdAt = parseDate(data.created_at);
		const updatedAt = parseDate(data.updated_at);
		if (!createdAt) fileErrors.push("created_at must be YYYY-MM-DD");
		if (!updatedAt) fileErrors.push("updated_at must be YYYY-MM-DD");

		if (!isStringArray(data.references)) {
			fileErrors.push("references must be an array of strings (can be empty)");
		}
		if (!isIntegerArray(data.related_issues)) {
			fileErrors.push(
				"related_issues must be an array of integers (can be empty)"
			);
		}
		if (!isIntegerArray(data.related_prs)) {
			fileErrors.push(
				"related_prs must be an array of integers (can be empty)"
			);
		}

		const staleExemptUntilRaw = data.stale_exempt_until;
		const staleExemptReason = data.stale_exempt_reason;
		const staleExtensions = data.stale_extensions;

		if (staleExemptUntilRaw !== undefined) {
			const parsed = parseDate(staleExemptUntilRaw);
			if (!parsed) {
				fileErrors.push("stale_exempt_until must be YYYY-MM-DD when provided");
			} else if (updatedAt && parsed < updatedAt) {
				fileErrors.push(
					"stale_exempt_until must not be earlier than updated_at"
				);
			}
		}
		if (
			staleExemptReason !== undefined &&
			typeof staleExemptReason !== "string"
		) {
			fileErrors.push("stale_exempt_reason must be a string when provided");
		}
		if (staleExtensions !== undefined && !isNonNegativeInt(staleExtensions)) {
			fileErrors.push(
				"stale_extensions must be a non-negative integer when provided"
			);
		}

		if (isDraftPath(file) && status === "proposed" && updatedAt) {
			const today = new Date();
			const daysSinceUpdate = diffDays(updatedAt, today);
			if (daysSinceUpdate > STALE_DAYS) {
				const parsedExempt = staleExemptUntilRaw
					? parseDate(staleExemptUntilRaw)
					: null;
				if (!parsedExempt || parsedExempt < today) {
					fileErrors.push(
						`draft is stale (${daysSinceUpdate} days since updated_at) without valid stale_exempt_until`
					);
				}
				if (
					staleExemptUntilRaw &&
					(!staleExemptReason || staleExemptReason.trim() === "")
				) {
					fileErrors.push(
						"stale_exempt_reason is required when stale_exempt_until is set"
					);
				}
			} else if (staleExemptUntilRaw) {
				fileWarnings.push(
					"stale_exempt_until is set but draft is not stale yet (<=30 days)"
				);
			}
		}

		if (isDraftPath(file) && status && status !== "proposed") {
			fileWarnings.push(
				`draft has status "${status}" (consider elevating to plan/intent or align status)`
			);
		}

		for (const key of Object.keys(data)) {
			if (
				!REQUIRED_KEYS.includes(key) &&
				!key.startsWith("stale_exempt") &&
				key !== "stale_extensions"
			) {
				fileWarnings.push(`unknown field: ${key}`);
			}
		}

		if (fileErrors.length) errors.push({ file, messages: fileErrors });
		if (fileWarnings.length) warnings.push({ file, messages: fileWarnings });
	}

	for (const { file, messages } of warnings) {
		console.warn(`WARN: ${file}`);
		for (const msg of messages) console.warn(`  - ${msg}`);
	}

	if (errors.length) {
		for (const { file, messages } of errors) {
			console.error(`ERROR: ${file}`);
			for (const msg of messages) console.error(`  - ${msg}`);
		}
		Deno.exit(1);
	}
};

run().catch((err) => {
	console.error(err);
	Deno.exit(1);
});

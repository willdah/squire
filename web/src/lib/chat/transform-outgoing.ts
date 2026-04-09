import { expandMentionsInText } from "./mention-candidates";
import { transformSlashMessage } from "./slash-commands";

/** Expand slash commands (first line) then @mentions; persisted message matches this string. */
export function transformOutgoingMessage(text: string, expansionByToken: Map<string, string>): string {
  const trimmed = text.trim();
  if (!trimmed) return text;
  const slashOut = transformSlashMessage(trimmed);
  const base = slashOut ?? trimmed;
  return expandMentionsInText(base, expansionByToken);
}

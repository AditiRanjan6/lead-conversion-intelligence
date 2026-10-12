export function escapeCsvCell(value: unknown): string {
  let text = value === null || value === undefined ? "" : String(value);
  const formulaIndex = text.search(/[=+\-@]/);
  if (
    formulaIndex >= 0 &&
    [...text.slice(0, formulaIndex)].every(
      (character) => character.trim() === "" || character.charCodeAt(0) <= 31,
    )
  ) {
    text = `'${text}`;
  }
  return `"${text.replace(/"/g, '""')}"`;
}

// Non-component helpers shared by ChannelFieldsForm and its callers - kept
// in their own (non-JSX) file so component files only export components
// (keeps React Fast Refresh happy, per oxlint's react/only-export-components
// rule).

export interface ChannelFieldValues {
  name: string;
  number: string;
  logoUrl: string;
  tvgId: string;
  sourceStreamUrl: string;
}

export const emptyChannelFieldValues: ChannelFieldValues = {
  name: '',
  number: '',
  logoUrl: '',
  tvgId: '',
  sourceStreamUrl: '',
};

/**
 * Converts the form's string fields into the optional (`string | null`)
 * shape the backend's add/update channel bodies expect - a blank field
 * means "no value", not the literal empty string.
 */
export function toChannelRequestBody(values: ChannelFieldValues) {
  const trimOrNull = (value: string) => (value.trim() === '' ? null : value.trim());
  return {
    name: values.name.trim(),
    number: trimOrNull(values.number),
    logoUrl: trimOrNull(values.logoUrl),
    tvgId: trimOrNull(values.tvgId),
    sourceStreamUrl: trimOrNull(values.sourceStreamUrl),
  };
}

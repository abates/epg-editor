// xmltv_id format is `ChannelID.cc@FeedID`, e.g. `WCBSTV.us@SD` [FR-E-2]
export const XMLTV_ID_PATTERN = /^[A-Za-z0-9]+\.[a-z]{2}(@[A-Za-z0-9]+)?$/

export interface XmltvIdParts {
  channel: string
  country: string
  feed: string | null
}

export function parseXmltvId(xmltvId: string): XmltvIdParts | null {
  if (!XMLTV_ID_PATTERN.test(xmltvId)) return null

  const [channel, feed] = xmltvId.split('@')

  return { channel, country: channel.slice(-2), feed: feed ?? null }
}

export function countryFromXmltvId(xmltvId: string): string | null {
  return parseXmltvId(xmltvId)?.country ?? null
}

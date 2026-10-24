import { services } from '$lib/server/services'
import type { PageServerLoad } from './$types'

// FR-V-1: in-app episode guide viewer, built from the file FR-R-5 is currently serving
export const load: PageServerLoad = async ({ params }) => services.guideView(params.slug)

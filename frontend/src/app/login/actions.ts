'use server'

import { headers } from 'next/headers'
import { redirect } from 'next/navigation'
import { createClient } from '@/utils/supabase/server'
import { getURL } from '@/utils/url'

async function getRedirectBaseUrl() {
  const headerStore = await headers()
  const forwardedHost = headerStore.get('x-forwarded-host')
  const forwardedProto = headerStore.get('x-forwarded-proto')
  const host = forwardedHost ?? headerStore.get('host')

  if (host) {
    const protocol = forwardedProto ?? (host.includes('localhost') ? 'http' : 'https')
    return `${protocol}://${host}/`
  }

  return getURL()
}

export async function loginWithGoogle() {
  const supabase = await createClient()
  const redirectBaseUrl = await getRedirectBaseUrl()

  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: {
      redirectTo: `${redirectBaseUrl}auth/callback`,
    },
  })

  if (error) {
    redirect('/login?message=' + encodeURIComponent(error.message))
  }

  if (data.url) {
    redirect(data.url)
  }
}

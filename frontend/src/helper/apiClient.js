import supabase from './supabaseClient';

/**
 * Helper function to make authenticated API calls
 * Automatically includes Supabase JWT token in Authorization header
 */
export async function apiCall(url, options = {}) {
  // Get the current session from Supabase
  const { data: { session } } = await supabase.auth.getSession();
  
  // Prepare headers
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };
  
  // Add Authorization header if we have a session
  if (session?.access_token) {
    headers['Authorization'] = `Bearer ${session.access_token}`;
  }
  
  // Make the API call
  const response = await fetch(url, {
    ...options,
    headers,
    credentials: 'include', // Include cookies for Replit auth compatibility
  });
  
  return response;
}

/**
 * Helper function to make authenticated API calls and parse JSON response
 */
export async function apiCallJson(url, options = {}) {
  const response = await apiCall(url, options);
  const data = await response.json();
  return { response, data };
}

export default apiCall;



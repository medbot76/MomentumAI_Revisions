import { useState, useEffect } from 'react';
import { API_ENDPOINTS } from '../config';

export function useAuth() {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchUser();
  }, []);

  const fetchUser = async () => {
    try {
      // Fetch user from Replit database via backend
      const response = await fetch(API_ENDPOINTS.AUTH_USER, {
        credentials: 'include', // Important for session cookies
      });
      if (response.ok) {
        const data = await response.json();
        if (data) {
          setUser(data);
        } else {
          setUser(null);
        }
      } else {
        setUser(null);
      }
    } catch (error) {
      console.error('Error fetching user:', error);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  };

  const login = () => {
    // Redirect to login page
    window.location.href = '/login';
  };

  const logout = async () => {
    try {
      // Call backend logout endpoint
      await fetch(API_ENDPOINTS.AUTH_LOGOUT, {
        method: 'POST',
        credentials: 'include',
      });
      setUser(null);
      window.location.href = '/login';
    } catch (error) {
      console.error('Error logging out:', error);
      setUser(null);
      window.location.href = '/login';
    }
  };

  return {
    user,
    isLoading,
    isAuthenticated: !!user,
    login,
    logout,
    refetch: fetchUser
  };
}

export default useAuth;

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
      const response = await fetch(API_ENDPOINTS.AUTH_USER, {
        credentials: 'include'
      });
      if (response.ok) {
        const data = await response.json();
        setUser(data);
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
    window.location.href = API_ENDPOINTS.LOGIN;
  };

  const logout = () => {
    window.location.href = API_ENDPOINTS.LOGOUT;
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

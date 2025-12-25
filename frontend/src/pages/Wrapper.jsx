import React, {useEffect, useState} from 'react'
import { Navigate } from 'react-router-dom'
import { API_ENDPOINTS } from '../config'

function Wrapper({children}) {
    const [authenticated, setAuthenticated] = useState(false)
    const [user, setUser] = useState(null)
    const [loading, setLoading] = useState(true)
    
    useEffect(() => {
        const checkAuth = async () => {
            try {
                const response = await fetch(API_ENDPOINTS.AUTH_USER, {
                    credentials: 'include'
                });
                const data = await response.json();
                
                if (data.authenticated && data.user) {
                    setAuthenticated(true);
                    setUser(data.user);
                } else {
                    setAuthenticated(false);
                    setUser(null);
                }
            } catch (error) {
                console.error('Auth check failed:', error);
                setAuthenticated(false);
                setUser(null);
            }
            setLoading(false);
        };

        checkAuth();
    }, []);

    if (loading){
        return <div className="flex items-center justify-center min-h-screen">Loading...</div>
    } else {
        if(authenticated){
            return React.cloneElement(children, { user });
        }
        return <Navigate to="/login"/>
    }
}

export default Wrapper

import React from 'react'
import { useAuth } from '../hooks/useAuth'

function Wrapper({children}) {
    const { user, isLoading, isAuthenticated, login } = useAuth();
    
    if (isLoading) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-gray-50">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-4 border-gray-200 border-t-gray-900 mx-auto mb-4"></div>
                    <p className="text-gray-600 font-medium">Loading...</p>
                </div>
            </div>
        );
    }
    
    if (!isAuthenticated) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-gray-50">
                <div className="w-full max-w-md mx-4">
                    <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-10 md:p-12 flex flex-col items-center">
                        {/* Logo */}
                        <div className="flex items-center gap-3 mb-8">
                            <img 
                                src="/medbotlogonew.jpg" 
                                alt="Momentum AI Logo" 
                                className="w-10 h-10 rounded-xl object-cover"
                            />
                            <span className="font-semibold text-2xl text-gray-900">Momentum AI</span>
                        </div>
                        
                        <h1 className="text-3xl font-semibold text-gray-900 mb-3 text-center">Welcome to MedBot</h1>
                        <p className="text-gray-600 text-center mb-8 text-base">Your AI-powered medical study assistant</p>
                        
                        <button
                            onClick={login}
                            className="w-full bg-black text-white hover:bg-gray-800 font-medium py-3.5 px-6 rounded-xl transition-all duration-200 text-base"
                        >
                            Sign in to Continue
                        </button>
                        
                        <p className="text-gray-500 text-sm mt-6 text-center">
                            New here? You can create an account after signing in
                        </p>
                    </div>
                </div>
            </div>
        );
    }
    
    return <>{children}</>;
}

export default Wrapper

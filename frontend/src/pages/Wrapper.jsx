import React from 'react'
import { useAuth } from '../hooks/useAuth'

function Wrapper({children}) {
    const { user, isLoading, isAuthenticated, login } = useAuth();
    
    if (isLoading) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-gray-50">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
                    <p className="text-gray-600">Loading...</p>
                </div>
            </div>
        );
    }
    
    if (!isAuthenticated) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-gray-50">
                <div className="w-full max-w-sm bg-white rounded-xl shadow p-8 flex flex-col items-center border border-gray-200">
                    <div className="flex items-center justify-center w-14 h-14 bg-blue-600 text-white rounded-lg mb-4">
                        <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                    </div>
                    <h1 className="text-2xl font-semibold text-gray-900 mb-2">Welcome to MedBot</h1>
                    <p className="text-sm text-gray-500 mb-6 text-center">Your AI-powered medical study assistant</p>
                    <button
                        onClick={login}
                        className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 rounded-lg transition-colors"
                    >
                        Sign in to Continue
                    </button>
                </div>
            </div>
        );
    }
    
    return <>{children}</>;
}

export default Wrapper

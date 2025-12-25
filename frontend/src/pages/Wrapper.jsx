import React from 'react'
import { useAuth } from '../hooks/useAuth'
import { useNavigate } from 'react-router-dom'

function Wrapper({children}) {
    const { user, isLoading, isAuthenticated, login } = useAuth();
    const navigate = useNavigate();
    
    if (isLoading) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-white">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-4 border-gray-200 border-t-gray-900 mx-auto mb-4"></div>
                    <p className="text-gray-600 font-medium">Loading...</p>
                </div>
            </div>
        );
    }
    
    if (!isAuthenticated) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-white">
                <div className="w-full max-w-lg px-6 md:px-8 py-12 md:py-16 text-center">
                    <h1 className="text-5xl md:text-6xl font-bold text-gray-900 mb-4">Log in or sign up</h1>
                    <p className="text-lg md:text-xl text-gray-600 mb-12">Get smarter responses and can upload files, images, and more.</p>
                    
                    <div className="space-y-3 mb-8">
                        <button
                            onClick={() => navigate('/login')}
                            className="w-full border border-gray-300 hover:border-gray-400 text-gray-900 font-medium py-3.5 px-6 rounded-full transition-all duration-200 flex items-center justify-center gap-3"
                        >
                            <span className="text-lg">📧</span>
                            Continue with Email
                        </button>
                    </div>
                    
                    <div className="flex items-center gap-3 mb-8">
                        <div className="flex-1 border-t border-gray-300"></div>
                        <span className="text-sm text-gray-500 font-medium">OR</span>
                        <div className="flex-1 border-t border-gray-300"></div>
                    </div>
                    
                    <div className="space-y-3">
                        <button
                            onClick={() => navigate('/register')}
                            className="w-full border border-gray-300 hover:border-gray-400 text-gray-900 font-medium py-3.5 px-6 rounded-full transition-all duration-200"
                        >
                            Sign up with Email
                        </button>
                    </div>
                </div>
            </div>
        );
    }
    
    return <>{children}</>;
}

export default Wrapper

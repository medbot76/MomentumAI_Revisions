// Configuration for API endpoints
const getApiBaseUrl = () => {
  return '';
};

export const API_BASE_URL = getApiBaseUrl();
export const API_ENDPOINTS = {
  CHAT: `${API_BASE_URL}/api/chat`,
  CHAT_STREAM: `${API_BASE_URL}/api/chat/stream`,
  UPLOAD: `${API_BASE_URL}/api/upload`,
  DOCUMENTS: `${API_BASE_URL}/api/documents`,
  TTS: `${API_BASE_URL}/api/tts`,
  STT: `${API_BASE_URL}/api/stt`,
  HEALTH: `${API_BASE_URL}/api/health`,
  EXAM_PDF: `${API_BASE_URL}/api/exam-pdf`,
  FLASHCARDS: `${API_BASE_URL}/api/flashcards`,
  MODELS: `${API_BASE_URL}/api/models`,
  SET_MODEL: `${API_BASE_URL}/api/model`,
  STUDYPLAN: `${API_BASE_URL}/api/studyplan`,
  STUDYPLAN_UPLOAD: `${API_BASE_URL}/api/studyplan-upload`,
  STUDYPLAN_ADD_TO_CALENDAR: `${API_BASE_URL}/api/studyplan/add-to-calendar`,
  AUTH_USER: `${API_BASE_URL}/api/auth/user`,
  AUTH_LOGIN: `${API_BASE_URL}/api/auth/login`,
  AUTH_SIGNUP: `${API_BASE_URL}/api/auth/signup`,
  AUTH_LOGOUT: `${API_BASE_URL}/api/auth/logout`,
  LOGIN: `${API_BASE_URL}/auth/replit_auth`, // Replit auth (legacy)
  LOGOUT: `${API_BASE_URL}/auth/logout`, // Replit auth (legacy)
}; 
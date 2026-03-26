import { initializeApp } from 'firebase/app';
import { getAnalytics } from 'firebase/analytics';

const firebaseConfig = {
  apiKey: "AIzaSyAdPcr2SZWE1LaI2AX-uCPErjnoAPz6uF4",
  authDomain: "trippy-eb159.firebaseapp.com",
  projectId: "trippy-eb159",
  storageBucket: "trippy-eb159.firebasestorage.app",
  messagingSenderId: "5704859155",
  appId: "1:5704859155:web:abad9887d517ec6eef49e6",
  measurementId: "G-TF211PNCGW",
};

const app = initializeApp(firebaseConfig);
export const analytics = getAnalytics(app);

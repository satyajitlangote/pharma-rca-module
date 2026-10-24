import { configureStore } from "@reduxjs/toolkit";
import rcaReducer from "./rcaSlice";

/**
 * Single store. All RCA state lives in the `rca` slice (form draft, AI
 * extraction preview, live analysis steps, saved investigations, UI state).
 * Components use useDispatch/useSelector from react-redux directly.
 */
export const store = configureStore({
  reducer: {
    rca: rcaReducer,
  },
});

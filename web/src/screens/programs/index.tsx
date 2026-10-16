import { Navigate, Route, Routes } from 'react-router-dom';
import { BenchScreen } from './Bench';
import { NodeScreen, ProgramsHome } from './Catalog';
import { EnrollmentScreen } from './Enrollment';
import { ProgramCardScreen } from './ProgramCard';

/** Вложенные маршруты `#/programs/*`. В App.tsx подключается одной строкой. */
export function ProgramsRoutes() {
  return (
    <Routes>
      <Route index element={<ProgramsHome />} />
      <Route path="node/:slug" element={<NodeScreen />} />
      <Route path="p/:slug" element={<ProgramCardScreen />} />
      <Route path="my/:id" element={<EnrollmentScreen />} />
      <Route path="session/:sid" element={<BenchScreen />} />
      <Route path="*" element={<Navigate to="/programs" replace />} />
    </Routes>
  );
}

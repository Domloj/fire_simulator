import { FC } from 'react';
import { useDispatch } from 'react-redux';
import { updateConfiguration } from '../../store/mapConfigurationSlice';
import {
  ConfigArrayForm,
  ConfigFormDropDown,
  ConfigFormTextField,
  ConfigGridContainer,
  ItemFormPartProps,
} from './configuration';
import { getDefaultSector, Sector, SectorTypes } from '../../model/sector';
import { useFormikContext } from 'formik';
import { Configuration } from '../../model/configuration';
import { Directions } from '../../model/geography';
import { Booleanify } from '@shared/utils/Booleanify';
import { Typography } from '@mui/material';
import { simulationService } from '../../services/api';

const objectName = 'sectors';

export const SectorFormPart: FC<ItemFormPartProps<Sector>> = ({ readonly, obj: sector }) => {
  const dispatch = useDispatch();
  const { values } = useFormikContext<Configuration>();

  const sectorIdx = values.sectors.findIndex((sec) => sec.sectorId === sector.sectorId);
  if (sectorIdx === -1) {
    return (
      <Typography variant={'body1'}>Sector {sector.sectorId} - couldn&apos;t find this sector in the list</Typography>
    );
  }

  return (
    <ConfigGridContainer>
      <ConfigFormTextField
        objectName={objectName}
        propertyName={'sectorId'}
        idx={sectorIdx}
        readOnly={true}
        type={'number'}
      />
      <ConfigFormTextField
        objectName={objectName}
        propertyName={'row'}
        idx={sectorIdx}
        readOnly={true}
        type={'number'}
      />
      <ConfigFormTextField
        objectName={objectName}
        propertyName={'column'}
        idx={sectorIdx}
        readOnly={true}
        type={'number'}
      />
      <ConfigFormDropDown
        objectName={objectName}
        allVariants={SectorTypes}
        propertyName={'sectorType'}
        idx={sectorIdx}
        readOnly={typeof readonly === 'boolean' ? readonly : readonly.sectorType}
      />
      <ConfigFormTextField
        objectName={objectName}
        propertyName={'initialState.temperature'}
        idx={sectorIdx}
        type={'number'}
        readOnly={typeof readonly === 'boolean' ? readonly : readonly.initialState.temperature}
      />
      <ConfigFormTextField
        objectName={objectName}
        propertyName={'initialState.windSpeed'}
        idx={sectorIdx}
        type={'number'}
        readOnly={typeof readonly === 'boolean' ? readonly : readonly.initialState.windSpeed}
      />
      <ConfigFormDropDown
        allVariants={Directions}
        objectName={objectName}
        propertyName={'initialState.windDirection'}
        idx={sectorIdx}
        readOnly={typeof readonly === 'boolean' ? readonly : readonly.initialState.windDirection}
      />
      <ConfigFormTextField
        objectName={objectName}
        propertyName={'initialState.airHumidity'}
        idx={sectorIdx}
        type={'number'}
        readOnly={typeof readonly === 'boolean' ? readonly : readonly.initialState.airHumidity}
      />
      <ConfigFormTextField
        objectName={objectName}
        propertyName={'initialState.plantLitterMoisture'}
        idx={sectorIdx}
        type={'number'}
        readOnly={typeof readonly === 'boolean' ? readonly : readonly.initialState.plantLitterMoisture}
      />
      <ConfigFormTextField
        objectName={objectName}
        propertyName={'initialState.co2Concentration'}
        idx={sectorIdx}
        type={'number'}
        readOnly={typeof readonly === 'boolean' ? readonly : readonly.initialState.co2Concentration}
      />
      <ConfigFormTextField
        objectName={objectName}
        propertyName={'initialState.pm2_5Concentration'}
        idx={sectorIdx}
        type={'number'}
        readOnly={typeof readonly === 'boolean' ? readonly : readonly.initialState.pm2_5Concentration}
      />
      {/* Assigned brigades for this sector - multiple select of brigade IDs */}
      <ConfigFormDropDown
        objectName={objectName}
        propertyName={'assignedBrigades'}
        idx={sectorIdx}
        allVariants={values.fireBrigades.map((b) => `${b.fireBrigadeId}`)}
        multiple={true}
        readOnly={typeof readonly === 'boolean' ? readonly : readonly.assignedBrigades}
      />
      {/* Apply assignment to simulation service instantly */}
      <div>
        <button
          type="button"
          onClick={async () => {
            const assigned = values.sectors[sectorIdx].assignedBrigades || [];
            const mapped = assigned.map((b: any) => Number(b));
            const payload = {
              sectorId: sector.sectorId,
              assignedBrigades: mapped,
            };

            try {
              await simulationService.assignBrigades(payload);
            } catch (error) {
              console.error('[SectorConfiguration] Failed to assign brigades:', error);
                return;
              }

              // Optimistically update UI so assignment is visible immediately.
              const sectorState = {
                temperature: sector.initialState.temperature,
                windSpeed: sector.initialState.windSpeed,
                windDirection: sector.initialState.windDirection,
                airHumidity: sector.initialState.airHumidity,
                plantLitterMoisture: sector.initialState.plantLitterMoisture,
                co2Concentration: sector.initialState.co2Concentration,
                pm2_5Concentration: sector.initialState.pm2_5Concentration,
                timestamp: Date.now(),
                fireLevel: sector.initialState.fireLevel ?? null,
                burnLevel: sector.initialState.burnLevel ?? null,
                extinguishLevel: sector.initialState.extinguishLevel ?? null,
              };

              // Dispatch configuration update so the UI reflects assignment immediately
              // This will be reconciled with SSE state when next tick arrives
              dispatch(updateConfiguration({
                configurationUpdate: {
                  forestName: '',
                  timestamp: new Date().toISOString(),
                  sectors: [{ sectorId: sector.sectorId, state: sectorState, contours: sector.contours, assignedBrigades: mapped }],
                  fireBrigades: [],
                  foresterPatrols: [],
                }
              }));
          }}
        >Apply assignment</button>
      </div>
    </ConfigGridContainer>
  );
};

type SectorsFormPartProps = {
  readonly: boolean | Booleanify<Sector>;
};

export const SectorsFormPart: FC<SectorsFormPartProps> = ({ readonly }) => {
  const { values } = useFormikContext<Configuration>();

  return (
    <ConfigArrayForm
      name={'sectors'}
      ChildForm={SectorFormPart}
      defaultObj={getDefaultSector()}
      data={values.sectors}
      readonly={readonly}
    />
  );
};

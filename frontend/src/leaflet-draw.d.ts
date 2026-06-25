import "leaflet";

declare module "leaflet-draw";

declare module "leaflet" {
  namespace Control {
    class Draw extends Control {
      constructor(options?: DrawOptions);
    }

    interface DrawOptions {
      draw?: DrawOptions.DrawOptions;
      edit?: DrawOptions.EditOptions;
    }

    namespace DrawOptions {
      interface DrawOptions {
        polygon?: DrawOptions.PolygonOptions | false;
        rectangle?: boolean | object;
        circle?: boolean | object;
        marker?: boolean | object;
        polyline?: boolean | object;
        circlemarker?: boolean | object;
      }

      interface PolygonOptions {
        allowIntersection?: boolean;
        shapeOptions?: PathOptions;
      }

      interface EditOptions {
        featureGroup: FeatureGroup;
      }
    }
  }

  namespace Draw {
    namespace Event {
      const CREATED: string;
      const EDITED: string;
      const DELETED: string;
    }
  }
}

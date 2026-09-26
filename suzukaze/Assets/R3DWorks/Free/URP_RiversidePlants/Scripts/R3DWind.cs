using UnityEngine;

namespace R3DWorks
{
    [RequireComponent(typeof(WindZone))]
    public class R3DWind : MonoBehaviour
    {

        private WindZone windZone;
        private Vector4 windVector = new Vector4();

        void Start()
        {
            windZone = GetComponent<WindZone>();
            UpdateShaderProps();
        }

        void UpdateShaderProps()
        {
            float force = windZone.windMain;
            Vector3 dir = transform.forward;
            windVector.Set(
                dir.x * force, 
                dir.y * force, 
                dir.z * force, 
                0.0f
            );
            Shader.SetGlobalVector("_R3DWindVector", windVector);
        }

        void FixedUpdate()
        {
            UpdateShaderProps();
        }
    }
}

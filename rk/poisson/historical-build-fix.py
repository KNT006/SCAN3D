from pathlib import Path
import subprocess
p=Path('/root/deploy/scan3d-flow-stl-build');f=p/'AdaptiveSolvers/Src/VertexFactory.inl'
pre=p/'AdaptiveSolvers/Src/PreProcessor.h';pre.write_text(pre.read_text().replace('#undef FAST_COMPILE','#define FAST_COMPILE'))
main=p/'AdaptiveSolvers/Src/PoissonRecon.cpp';text=main.read_text().replace('#define DEFAULT_FEM_DEGREE 1','#define DEFAULT_FEM_DEGREE 2')
# This deployment only consumes position+normal BNPTS, never auxiliary color data.
fast=text.index('#ifdef FAST_COMPILE',text.index('int main('));begin=text.find('\tchar *ext = GetFileExtension( In.value );',fast);end=text.find('\tdelete[] ext;',begin)
if begin>=0 and begin<text.index('#else // !FAST_COMPILE',fast):text=text[:begin]+'\tExecute< Real >( FEMSigs() , VertexFactory::EmptyFactory< Real >() );\n'+text[end+len('\tdelete[] ext;'):]
main.write_text(text)
s=f.read_text();s=s.replace('offsetof( VertexType , coords[idx] )','( offsetof( VertexType , coords ) + sizeof( Real ) * idx )').replace('offsetof( VertexType , coords[ idx ] )','( offsetof( VertexType , coords ) + sizeof( Real ) * idx )').replace('offsetof( VertexType , coords[idx%3] )','( offsetof( VertexType , coords ) + sizeof( Real ) * (idx%3) )');f.write_text(s)
log=open(p/'build-fixed.log','wb')
process=subprocess.Popen(['nice','-n','10','make','poissonrecon','-j1','CFLAGS_RELEASE=-O1 -DRELEASE -DFAST_COMPILE','LFLAGS_RELEASE=-O1'],cwd=p/'AdaptiveSolvers',stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
print(process.pid)
